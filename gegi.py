import krpc
import time
import serial
import threading
from si_prefix import si_format
from time_format import time_format
from ask_for_port import ask_for_port
from math import pi, sin, cos

# atomic serial write called from main loop and from threads
def myserwrite(line):
	global serialLock
	global ser
	with serialLock:
		ser.write(line)

# flush is called at the end of the loop, not from threads
lastflush = time.time()
def myserflush():
	global ser
	global lastflush
	print("Flush!"+str(round((time.time()-lastflush)*1000))+"\t")
	lastflush = time.time()
	ser.flush()

# thread to display status (G-force, LCD, OLED)
class StatusDisplays(threading.Thread):
	def __init__(self,orbit,flight,flightstream,lcdmode,oledmode,lastgforce,lastoledline,lastoledtime):
		super(StatusDisplays, self).__init__()
		self.lcdmode = lcdmode
		self.oledmode = oledmode
		self.lastgforce = lastgforce
		self.orbit = orbit
		self.flight = flight
		self.flightstream = flightstream
		self.lastoledtime = lastoledtime
		self.lastoledline = lastoledline
	def run(self):
		try:
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
			if self.lcdmode==0: # switch in middle = Orbit
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
				line = "P0=ALT:"+fval+"m\nP1=V:"+chr(2)
	#			print(str(ss)+"\t"+str(vs)+"\t"+str(self.flightstream().g_force)+"\t"+str(self.flight().g_force))
				fval = si_format(abs(self.flightstream().horizontal_speed), precision=0).rjust(5)[:5]
				line = line+fval+" "+chr(3)
				fval = si_format(abs(self.flightstream().vertical_speed), precision=0).rjust(5)[:5]
				line = line+fval+chr(1)+"\n"
			elif self.lcdmode==2: # switch on left = Target(?)
				line="P0=Mode 1 Left\nP1=Target mode\n"
				line="P0=Ecct.:"+str(round(self.orbit.eccentricity,3))+"\nP1=Incl.:"+str(round(self.orbit.inclination*180/pi,2))+chr(223)+"\n"
#			print("mode"+str(self.lcdmode)+" "+line)
			myserwrite(bytes([x for x in map(ord,line)]))
			# OLED orbit
			if (time.time()-self.lastoledtime)>2: # every 2s
				self.lastoledtime = time.time()
				if self.oledmode==0: # switch in middle = Orbit
					cx = int(128/2)
					cy = int(16+(64-16)/2)
					sx = self.orbit.semi_major_axis
					sy = self.orbit.semi_minor_axis
#					print("sx="+str(sx)+"\tsy="+str(sy)+"\n")
					try:
						scalex = sx/cx
						scaley = sy/((64-16)/2)
						scale = min(scalex,scaley)
						sx = int(sx/scale)
						sy = int(sy/scale)
						if sx==0: sx=1
						if sx>=64: sx=63
						if sy==0: sy=1
						if sy>=48: sy=47
						line="O5 "+str(int(cx-sx/2))+" "+str(cy)+" "+str(sx)+" "
						line=line+"6 "+str(cx)+" "+str(int(cy-sy/2))+" "+str(sy)+" "
						line=line+"9 "+str(cx)+" "+str(cy)+" "+str(int(sx/3))+" "+str(int(sy/3))+" "
						ec = pi/2-self.orbit.inclination
						sx = int(cx+24*sin(ec))
						sy = int(cy-24*cos(ec))
						line=line+"7 "+str(cx)+" "+str(cy)+" "+str(sx)+" "+str(sy)+"\n"
					except ValueError:
						line=self.lastoledline
				elif self.oledmode==1:
					line="O1 10 10 Mode1\\ \n"
				elif self.oledmode==2:
					line="O1 10 10 Mode2\\ \n"
#				print("omode"+str(self.oledmode)+"\\"+line+"\\")
				if line!=self.lastoledline:
					self.lastoledline=line
					myserwrite(line.encode())
		except krpc.error.RPCError:
			pass

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
		except krpc.error.RPCError:
			pass
		if ((self.temp_pct<0.6) and (self.overheat!=0)):
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
		try:
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
				self.lowfuel = 2
				myserwrite(b"LG10=0\nLR10=3\n")
		except krpc.error.RPCError:
			pass

# may throw krpc.error.RPCError if vessel no longer active/exists,
# should roll back to vessel = conn.space_center.active_vessel above loop

def main_serial_loop():
	global conn
	global vessel

	control  = vessel.control
	flightstream = conn.add_stream(vessel.flight,vessel.orbit.body.reference_frame)
	orbit	 = vessel.orbit

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
	lastoledline = None
	lastoledtime = time.time()

	request_rcs=None
	request_sas=None
	request_gear=None
	request_lights=None
	lastrcs=None
	lastsas=None
	lastgear=None
	lastlights=None
	lastd0=None
	lastd1=None
	lastd2=None
	lastd3=None
	lastd4=None
	lastd5=None
	stageabort=None

	try:
		while vessel == conn.space_center.active_vessel:
			while ser.inWaiting()>0:
				line = ser.readline().decode("utf-8").rstrip()
	#			print("Serial:["+line+"]\n----\n")
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
					request_rcs = False
					control.rcs = request_rcs
				if line=="D6=1":
					request_rcs = True
					control.rcs = request_rcs
				if line=="D7=0":
					request_sas = False
					control.sas = request_sas
				if line=="D7=1":
					request_sas = True
					control.sas = request_sas
				if line=="D5=0":
					request_gear = False
					control.gear = request_gear
				if line=="D5=1":
					request_gear = True
					control.gear = request_gear
				if line=="D4=0":
					request_lights = False
					control.lights = request_lights
				if line=="D4=1":
					request_lights = True
					control.lights = request_lights
				if line=="D3=1":
					lastd3 = 1
				if line=="D3=0":
					lastd3 = 0
				if line=="D2=0":
					lastd2 = 0
				if line=="D2=1":
					lastd2 = 1
				if line=="D1=1":
					lastd1 = 1
				if line=="D1=0":
					lastd1 = 0
				if line=="D0=0":
					lastd0 = 0
				if line=="D0=1":
					lastd0 = 1

			if lastd3==1:
				lcdmode = 2
			elif lastd2==1:
				lcdmode = 1
			else:
				lcdmode = 0 # middle=orbit apo/timeto/pery/timeto

			if lastd1==1:
				oledmode = 2
			elif lastd0==1:
				oledmode = 1
			else:
				oledmode = 0

			# handle switch state change
			if control.rcs!=request_rcs:
				reqval="3"
			else:
				reqval="0"
			if request_rcs:
				line = "LG6=1\nLR6="+reqval+"\n"
			else:
				line = "LG6="+reqval+"\nLR6=1\n"
			if line!=lastrcs:
				myserwrite(line.encode())
				lastrcs = line

			if control.sas!=request_sas:
				reqval="3"
			else:
				reqval="0"
			if request_sas:
				line = "LG7=1\nLR7="+reqval+"\n"
			else:
				line = "LG7="+reqval+"\nLR7=1\n"
			if line!=lastsas:
				myserwrite(line.encode())
				lastsas = line

			if control.gear!=request_gear:
				reqval="3"
			else:
				reqval="0"
			if request_gear:
				line = "LG5=1\nLR5="+reqval+"\n"
			else:
				line = "LG5="+reqval+"\nLR5=1\n"
			if line!=lastgear:
				myserwrite(line.encode())
				lastgear = line

			if control.lights!=request_lights:
				reqval="3"
			else:
				reqval="0"
			if request_lights:
				line = "LG4=1\nLR4="+reqval+"\n"
			else:
				line = "LG4="+reqval+"\nLR4=1\n"
			if line!=lastlights:
				myserwrite(line.encode())
				lastlights = line

			# Status
			if statusthread == None:
				statusthread = StatusDisplays(orbit,vessel.flight,flightstream,lcdmode,oledmode,lastgforce,lastoledline,lastoledtime)
				statusthread.start()
			elif not statusthread.is_alive():
				lastgforce = statusthread.lastgforce
				lastoledline = statusthread.lastoledline
				lastoledtime = statusthread.lastoledtime
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
			myserflush()
	except krpc.error.RPCError:
		print("Exception")
	else:
		print("No exception, change of vessel")

def main():

	global serialLock
	serialLock = threading.Lock()

	global ser
	ser = serial.Serial(port=ask_for_port(),baudrate=115200,timeout=0,write_timeout=0)

	if not ser.isOpen():
		print("Can't open serial port!")

	global conn
	global vessel
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

	while True:
		vessel = None
		while vessel==None:
			try:
				vessel = conn.space_center.active_vessel
				print("Active vessel:"+vessel.name)
				line = "P0="+conn.krpc.get_status().version+"\n"
				line = line+"P1="+vessel.name+"\n"
				myserwrite(line.encode())
				time.sleep(.5)
				# ask for status
				myserwrite(b"R\n")
				main_serial_loop()
			except krpc.error.RPCError:
				print("Not in proper game scene")
				myserwrite("P0=Waiting for\nP1=game scene\n".encode())
				time.sleep(.5)

if __name__ == '__main__':
    main()
