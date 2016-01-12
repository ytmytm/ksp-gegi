import krpc
import time
import serial
import threading
from si_prefix import si_format
from time_format import time_format
from ask_for_port import ask_for_port

serialLock = threading.Lock()
lastflush = time.time()

ser = serial.Serial(port=ask_for_port(),baudrate=115200,timeout=0,write_timeout=0)

if not ser.isOpen():
	print("Can't open serial port!")

# atomic serial write called from main loop and from threads
def myserwrite(line):
	with serialLock:
		ser.write(line)

# flush is called at the end of the loop, not from threads
def myserflush():
	global lastflush
	print("Flush!"+str(round((time.time()-lastflush)*1000))+"\t")
	lastflush = time.time()
	ser.flush()

# thread to display status (G-force, LCD, OLED)
class StatusDisplays(threading.Thread):
	def __init__(self,orbit,flight,flightstream,lcdmode,oledmode,lastgforce):
		super(StatusDisplays, self).__init__()
		self.lcdmode = lcdmode
		self.oledmode = oledmode
		self.lastgforce = lastgforce
		self.orbit = orbit
		self.flight = flight
		self.flightstream = flightstream
	def run(self):
		# g-force changed enough?
		newgforce = self.flight().g_force
		if (abs(newgforce-self.lastgforce)>0.01):
			self.lastgforce = newgforce
			newgforce = min(abs(newgforce),5)
			newgforce = int(newgforce*255/5)
			gforcecommand = "A0="+str(newgforce)+"\n"
#			print(gforcecommand)
			myserwrite(gforcecommand.encode())
		# LCD
		if self.lcdmode==0: # switch on middle = Orbit
			val = self.orbit.apoapsis_altitude
			if val>=0:
				fval = si_format(val, precision=2).rjust(7)[:7]+" "
			else:
				fval = si_format(val, precision=2).rjust(8)[:8]
			line = "P0=A:"+fval+time_format(self.orbit.time_to_apoapsis)+"\n"
			val = self.orbit.periapsis_altitude
			if val>=0:
				fval = si_format(val, precision=2).rjust(7)[:7]+" "
			else:
				fval = si_format(val, precision=2).rjust(8)[:8]
			line = line+"P1=P:"+fval+time_format(self.orbit.time_to_periapsis)+"\n"
		elif self.lcdmode==1: # switch on right = Landing Altitude+Speed
			fval = si_format(self.flight().surface_altitude, precision=3).rjust(8)[:8]
			line = "P0=ALT:"+fval+"m\nP1=V"+chr(126)
			ss = self.flightstream().speed
			vs = self.flightstream().vertical_speed
#			print(str(ss)+"\t"+str(vs)+"\t"+str(self.flightstream().g_force)+"\t"+str(self.flight().g_force))
			fval = si_format(abs((ss*ss-vs*vs)**(1/2)), precision=0).rjust(4)[:4]
			line = line+fval+" v"
			fval = si_format(abs(vs), precision=0).rjust(5)[:5]
			line = line+fval+"m/s\n"
		elif self.lcdmode==2: # switch on left = Target(?)
			line="P0=Mode 1 Left\nP1=Target mode\n"
		#print("mode"+str(lcdmode)+" "+line)
		myserwrite(line.encode())

# thread to calculate overheat [max(% temp/maxtemp) for each part]
class TempMax(threading.Thread):
	def __init__(self,parts,overheat):
		super(TempMax, self).__init__()
		self.overheat = overheat
		self.parts = parts
		self.temp_pct = 0
	def run(self):
		try:
			self.temp_pct=max([max(part.temperature/part.max_temperature,part.skin_temperature/part.max_skin_temperature) for part in self.parts])
		except ValueError:
			self.temp_pct = 0
		if ((self.temp_pct<0.6) and (overheat!=0)):
			self.overheat = 0
			myserwrite(b"LG12=1\nLR12=0\n")
		if ((self.temp_pct>=0.6) and (self.temp_pct<0.8) and (self.overheat!=1)):
			self.overheat = 1
			myserwrite(b"LG12=0\nLR12=1\n")
		if ((self.temp_pct>=0.8) and (self.overheat!=2)):
			self.overheat = 2
			myserwrite(b"LG12=0\nLR12=3\n")
#		threading.Thread.__init__(self) # this allows to call start() again on this thread, but the vessel may have lost parts in the meantime

# thread to calculate low power/low fuel
class LowResources(threading.Thread):
	def __init__(self,resources,lowpower,lastpowerpct,lowfuel):
		super(LowResources, self).__init__()
		self.resources = resources
		self.lowpower = lowpower
		self.power_pct = 0
		self.lastpowerpct = lastpowerpct
		self.lowfuel = lowfuel
		self.fuel_pct = 0
	def run(self):
		# power
		rmax = self.resources.max('ElectricCharge')
		if rmax>0:
			self.power_pct = self.resources.amount('ElectricCharge')/rmax
		if (abs(self.power_pct-self.lastpowerpct)>0.01):
			self.lastpowerpct = self.power_pct
			powercommand = "A1="+str(int(self.power_pct*255))+"\n"
			myserwrite(powercommand.encode())
		if ((self.power_pct>=.2) and (self.lowpower!=0)):
			self.lowpower = 0
			myserwrite(b"LG11=1\nLR11=0\n")
		if ((self.power_pct<.2) and (self.power_pct>.1) and (self.lowpower!=1)):
			self.lowpower = 1
			myserwrite(b"LG11=0\nLR11=1\n")
		if ((self.power_pct<=.1) and (self.lowpower!=2)):
			self.lowpower = 2
			myserwrite(b"LG11=0\nLR11=3\n")
		rmax = self.resources.max('LiquidFuel')
		if rmax>0:
			self.fuel_pct = self.resources.amount('LiquidFuel')/rmax
		# fuel
		if (((self.fuel_pct>=.2) or (self.fuel_pct==0)) and (self.lowfuel!=0)):
			self.lowfuel = 0
			myserwrite(b"LG10=1\nLR10=0\n")
		if ((self.fuel_pct<.2) and (self.fuel_pct>.1) and (self.lowfuel!=1)):
			self.lowfuel = 1
			myserwrite(b"LG10=0\nLR10=1\n")
		if ((self.fuel_pct<=.1) and (self.fuel_pct>0) and (self.lowfuel!=2)):
			lowpower = 2
			myserwrite(b"LG10=0\nLR10=3\n")

conn = None
print("Connecting to Kerbal Space Program kRPC\n")
myserwrite("P0=Connecting to\nP1=Kerbal Space Prg\n".encode())
while conn==None:
	try:
		conn = krpc.connect(name='Arduino')
	except (krpc.error.NetworkError,ConnectionRefusedError):
		print("Connection refused, waiting 5s")
		myserwrite("P1=Connecting...\n".encode())
		time.sleep(5)

print("Connection successful "+conn.krpc.get_status().version)

vessel = None
while vessel==None:
	try:
		vessel = conn.space_center.active_vessel
	except krpc.error.RPCError:
		print("Not in proper game scene")
		myserwrite("P0=Waiting for\nP1=game scene\n".encode())
		time.sleep(.5)

print("Active vessel:"+vessel.name)
line = "P0="+conn.krpc.get_status().version+"\n"
line = line+"P1="+vessel.name+"\n"
myserwrite(line.encode())
time.sleep(.5)

# ask for status
myserwrite(b"R\n")

control  = vessel.control
flightstream = conn.add_stream(vessel.flight,vessel.orbit.body.reference_frame)
orbit	 = vessel.orbit

lastrcs = control.rcs
lastsas = control.sas
lastgear = control.gear
lastlights = control.lights
stageabort = False

# may throw krpc.error.RPCError if vessel no longer active/exists,
# should roll back to vessel = conn.space_center.active_vessel above loop

# do temperature/overheat estimation in separate thread so command & control is not blocked by this
temperature = None
temp_pct = -1
overheat = -1
# do electric power estimation and low fuel in separate thread so command & control is not blocked by this
resourcethread = None
power_pct = -1
lowpower = -1
fuel_pct = -1
lowfuel  = -1
# do status display (G-force, LCD, OLED) in separate thread so command & control is not blocked by this
statusthread = None
lastgforce = -100
lcdmode = 0
oledmode = 0

while True:
	#print("---------CONTROL")
	#print("SAS:"+str(control.sas)+"\tRCS:"+str(control.rcs))
	#print("Gear:"+str(control.gear)+"\tLights:"+str(control.lights))
	#print("Throttle:"+str(control.throttle))
	#print("---------ORBIT")
	#print("Speed:"+str(round(orbit.speed,2)))
	#print("Apoapsis:"+str(round(orbit.apoapsis_altitude,0))+"\tPeriapsis:"+str(round(orbit.periapsis_altitude,0)))
	#print("Time to:"+str(round(orbit.time_to_apoapsis,0))+" s\tTime to:  "+str(round(orbit.time_to_periapsis,0))+" s")
	#print("---------FLIGHT")
	#print("Altitude: "+str(round(flight().mean_altitude,0))+"\tSpeed: "+str(round(speed().speed,2)))
	#print("Pitch :"+str(round(flight().pitch,1))+"\tRoll :"+str(round(flight().roll,1))+"\t Head :"+str(round(flight().heading,1)))

	# serial link
	if ser.isOpen():
		while ser.inWaiting()>0:
			line = ser.readline().decode("utf-8").rstrip()
#			print("Serial:["+line+"]\n----\n")
			if line=="I":
				lastrcs=None
				lastsas=None
				lastgear=None
				lastlights=None
				lastgforce=-100
			if line[:3]=="P0=":
				control.throttle = int(line[3:],16)/255
			if line[:3]=="P1=":
				# timewarp
				newtimewarp = min(int(line[3:],16)/255/0.9,1)
				railslevel = int(newtimewarp*7)
				physlevel = int(newtimewarp*4)
				if (conn.space_center.warp_mode == conn.space_center.WarpMode.rails):
					conn.space_center.rails_warp_factor = railslevel
				elif (conn.space_center.warp_mode == conn.space_center.WarpMode.physics):
					conn.space_center.physics_warp_factor = physlevel
				else:
				# no time warp - try to set as rails, if failed then try to set as physics
					conn.space_center.rails_warp_factor = railslevel
					if (conn.space_center.warp_mode != conn.space_center.WarpMode.rails):
						conn.space_center.physics_warp_factor = physlevel
			if line=="D8=1":
				if stageabort:
					control.activate_next_stage()
				else:
					control.abort = True
			if line=="D9=1":
				stageabort = False; # left = abort
			if line=="D9=0":
				stageabort = True;  # right = stage
			if line=="D6=0":
				control.rcs=False
			if line=="D6=1":
				control.rcs=True
			if line=="D7=0":
				control.sas=False
			if line=="D7=1":
				control.sas=True
			if line=="D5=0":
				control.gear=False
			if line=="D5=1":
				control.gear=True
			if line=="D4=0":
				control.lights=False
			if line=="D4=1":
				control.lights=True
			if line=="D3=1":
				lcdmode = 2 # left=target
			if line=="D3=0":
				lcdmode = 0 # middle=orbit
			if line=="D2=0":
				lcdmode = 0 # middle=orbit
			if line=="D2=1":
				lcdmode = 1 # right=surface

		# Status
		if statusthread == None:
			statusthread = StatusDisplays(orbit,vessel.flight,flightstream,lcdmode,oledmode,lastgforce)
			statusthread.start()
		elif not statusthread.is_alive():
			lastgforce = statusthread.lastgforce
			statusthread = None
		# Warnings
		# overheat <0.6, .8-.9, >.9
		if temperature == None:
			temperature = TempMax(vessel.parts.all,overheat)
			temperature.start()
		elif not temperature.is_alive():
			temp_pct = temperature.temp_pct
			overheat = temperature.overheat
			temperature = None
#			print("Max heat: "+str(round(temp_pct*100,0)))
		# power
		if resourcethread == None:
			resourcethread = LowResources(vessel.resources,lowpower,power_pct,lowfuel)
			resourcethread.start()
		elif not resourcethread.is_alive():
			power_pct = resourcethread.power_pct
			lowpower = resourcethread.lowpower
			fuel_pct = resourcethread.fuel_pct
			lowfuel = resourcethread.lowfuel
			resourcethread = None
#			print("Power: "+str(round(power_pct*100,0))+" ("+str(lowpower)+")\tL.fuel: "+str(round(fuel_pct*100,0))+" ("+str(lowpower)+")")

		# serial state change
		if control.rcs!=lastrcs:
			lastrcs = control.rcs
			if lastrcs:
				myserwrite(b"LG6=1\nLR6=0\n")
			else:
				myserwrite(b"LG6=0\nLR6=1\n")
		if control.sas!=lastsas:
			lastsas = control.sas
			if lastsas:
				myserwrite(b"LG7=1\nLR7=0\n")
			else:
				myserwrite(b"LG7=0\nLR7=1\n")
		if control.gear!=lastgear:
			lastgear = control.gear
			if lastgear:
				myserwrite(b"LG5=1\nLR5=0\n")
			else:
				myserwrite(b"LG5=0\nLR5=1\n")
		if control.lights!=lastlights:
			lastlights = control.lights
			if lastlights:
				myserwrite(b"LG4=1\nLR4=0\n")
			else:
				myserwrite(b"LG4=0\nLR4=1\n")
	myserflush()
#	time.sleep(.1)
