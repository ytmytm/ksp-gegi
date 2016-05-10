import krpc
import time
import serial
import threading
import sys
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
	if (ser.out_waiting>0):
		ser.flush()
		lastflush = time.time()
		print("Flush!"+str(round((time.time()-lastflush)*1000))+"\t"+str(ser.out_waiting))

# thread to display status (G-force, LCD, OLED)
class StatusDisplays(threading.Thread):
	def __init__(self,flightstream,flightstreamorbital,lcdmode,oledmode,lastgforce,lastoledline,lastoledtime,orbitstreamapoalt,orbitstreamapotime,orbitstreamperialt,orbitstreamperitime,orbitstreamecc,orbitstreamincl,orbitstreamsemimajor,orbitstreamsemiminor):
		super(StatusDisplays, self).__init__()
		self.lcdmode = lcdmode
		self.oledmode = oledmode
		self.lastgforce = lastgforce
		self.flightstream = flightstream
		self.flightstreamorbital = flightstreamorbital
		self.lastoledtime = lastoledtime
		self.lastoledline = lastoledline
		self.orbitstreamapoalt = orbitstreamapoalt
		self.orbitstreamapotime = orbitstreamapotime
		self.orbitstreamperialt = orbitstreamperialt
		self.orbitstreamperitime = orbitstreamperitime
		self.orbitstreamecc = orbitstreamecc
		self.orbitstreamincl = orbitstreamincl
		self.orbitstreamsemiminor = orbitstreamsemiminor
		self.orbitstreamsemimajor = orbitstreamsemimajor
	def run(self):
		try:
			# g-force changed enough?
			newgforce = self.flightstream().g_force
			if (abs(newgforce-self.lastgforce)>0.01):
				self.lastgforce = newgforce
				newgforce = min(abs(newgforce),5)
				newgforce = int(newgforce*255/5)
				gforcecommand = "A0="+str(newgforce)+"\n"
	#			print(gforcecommand)
				myserwrite(gforcecommand.encode())
			# LCD
			if self.lcdmode==0: # switch in middle = Orbit
				val = self.orbitstreamapoalt()
				if val>=0:
					fval = si_format(val, precision=2).rjust(7)[:7]+" "
				else:
					fval = si_format(val, precision=2).rjust(8)[:8]
				line = "P0=A:"+fval+time_format(self.orbitstreamapotime())+"\n"
				val = self.orbitstreamperialt()
				if val>=0:
					fval = si_format(val, precision=2).rjust(7)[:7]+" "
				else:
					fval = si_format(val, precision=2).rjust(8)[:8]
				line = line+"P1=P:"+fval+time_format(self.orbitstreamperitime())+"\n"
			elif self.lcdmode==1: # switch on right = Landing Altitude+Speed
				fval = si_format(self.flightstream().surface_altitude, precision=3).rjust(8)[:8]
				line = "P0=ALT:"+fval+"m\nP1=V:"+chr(2)
	#			print(str(ss)+"\t"+str(vs)+"\t"+str(self.flightstream().g_force)+"\t"+str(self.flight().g_force))
				fval = si_format(abs(self.flightstream().horizontal_speed), precision=0).rjust(5)[:5]
				line = line+fval+" "+chr(3)
				fval = si_format(abs(self.flightstream().vertical_speed), precision=0).rjust(5)[:5]
				line = line+fval+chr(1)+"\n"
			elif self.lcdmode==2: # switch on left = Target(?)
				line="P0=Mode 1 Left\nP1=Target mode\n"
				line="P0=Ecct.:"+str(round(self.orbitstreamecc(),3))+"\nP1=Incl.:"+str(round(self.orbitstreamincl()*180/pi,2))+chr(223)+"\n"
#			print("mode"+str(self.lcdmode)+" "+line)
			myserwrite(bytes([x for x in map(ord,line)]))
			# OLED orbit
			if (time.time()-self.lastoledtime)>.2: # every 1s
				self.lastoledtime = time.time()
				if self.oledmode==0: # switch in middle = Orbit
					cx = int(128/2)
					cy = int(16+(64-16)/2)
					sx = self.orbitstreamsemimajor()
					sy = self.orbitstreamsemiminor()
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
						ec = pi/2-self.orbitstreamincl()
						sx = int(cx+24*sin(ec))
						sy = int(cy-24*cos(ec))
						line=line+"7 "+str(cx)+" "+str(cy)+" "+str(sx)+" "+str(sy)+"\n"
					except ValueError:
						line=self.lastoledline
				elif self.oledmode==1:
          # map difference between direction and prograde to unit circle (navball like)
					prog = self.flightstreamorbital().prograde
					dir = self.flightstreamorbital().direction
          # these calculations are wrong...
					dx = prog[0]-dir[0]
					dy = prog[1]-dir[1]
					dz = prog[2]-dir[2]
					back = (dir[1]<0)
					sx = 40+48/2+int(dz*48/2)
					sy = 16+48/2+int(dx*48/2)
					line = "O4 64 40 O8 64 40 23 "
					if back:
					  line=line+"O3 "
					else:
					  line=line+"O2 "
					line=line+str(int(sx-2))+" "+str(int(sy-2))+" 5 5\n"
					print("sx="+str(int(sx))+"\tsy="+str(int(sy))+"\n")
				elif self.oledmode==2:
					line="O1 10 10 Mode2\\ \n"
				print("omode"+str(self.oledmode)+"\\"+line+"\\")
				if line!=self.lastoledline:
					self.lastoledline=line
					myserwrite(line.encode())
		except krpc.error.RPCError:
			pass

# may throw krpc.error.RPCError if vessel no longer active/exists,
# should roll back to vessel = conn.space_center.active_vessel above loop

def main_serial_loop():
	global conn
	global vessel

	control  = vessel.control
	flightstream = conn.add_stream(vessel.flight,vessel.orbit.body.reference_frame)
	flightstreamorbital = conn.add_stream(vessel.flight,vessel.orbital_reference_frame)
	maxtmpstream = conn.add_stream(conn.gegi.active_gegi.max_temp_pct)
	sasstream = conn.add_stream(getattr,vessel.control,'sas')
	rcsstream = conn.add_stream(getattr,vessel.control,'rcs')
	gearstream = conn.add_stream(getattr,vessel.control,'gear')
	lightstream = conn.add_stream(getattr,vessel.control,'lights')
	orbitstreamapoalt = conn.add_stream(getattr,vessel.orbit,'apoapsis_altitude')
	orbitstreamapotime = conn.add_stream(getattr,vessel.orbit,'time_to_apoapsis')
	orbitstreamperialt = conn.add_stream(getattr,vessel.orbit,'periapsis_altitude')
	orbitstreamperitime = conn.add_stream(getattr,vessel.orbit,'time_to_periapsis')
	orbitstreamecc = conn.add_stream(getattr,vessel.orbit,'eccentricity')
	orbitstreamincl = conn.add_stream(getattr,vessel.orbit,'inclination')
	orbitstreamsemimajor = conn.add_stream(getattr,vessel.orbit,'semi_major_axis')
	orbitstreamsemiminor = conn.add_stream(getattr,vessel.orbit,'semi_minor_axis')

	# do temperature/overheat estimation in separate thread so command & control is not blocked by this
	temp_pct = -1
	overheat = -1
	# do electric power estimation and low fuel in separate thread so command & control is not blocked by this
	resourcethread = None
	resourceelectricmaxstream = conn.add_stream(vessel.resources.max,'ElectricCharge')
	resourceelectriccurstream = conn.add_stream(vessel.resources.amount,'ElectricCharge')
	resourceliquidfuelmaxstream = conn.add_stream(vessel.resources.max,'LiquidFuel')
	resourceliquidfuelcurstream = conn.add_stream(vessel.resources.amount,'LiquidFuel')
	power_pct = -1
	lastpowerpct = 0
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
	laststageclear = True
	laststagetime = time.time()

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
					try:
						control.throttle = int(line[3:],16)/255
					except ValueError:
						print("Throttle conversion problem: ["+line+"]:\n")
				if line[:3]=="P1=":
					# timewarp
					try:
						newtimewarp = min(int(line[3:],16)/255/0.9,1)
					except ValueError:
						print("Timewarp conversion problem: ["+line+"]:\n")
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
            # stage
						if laststageclear and (time.time()-laststagetime)>1: # at least 1s delay between staging and D8 must be released between staging
							laststageclear = False
							laststagetime = time.time()
							control.activate_next_stage()
					else:
						control.abort = True
				if line=="D8=0":
					laststageclear = True # release D8
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
			if rcsstream()!=request_rcs:
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

			if sasstream()!=request_sas:
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

			if gearstream()!=request_gear:
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

			if lightstream()!=request_lights:
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
				statusthread = StatusDisplays(flightstream,flightstreamorbital,lcdmode,oledmode,lastgforce,lastoledline,lastoledtime,orbitstreamapoalt,orbitstreamapotime,orbitstreamperialt,orbitstreamperitime,orbitstreamecc,orbitstreamincl,orbitstreamsemimajor,orbitstreamsemiminor)
				statusthread.start()
			elif not statusthread.is_alive():
				lastgforce = statusthread.lastgforce
				lastoledline = statusthread.lastoledline
				lastoledtime = statusthread.lastoledtime
				statusthread = None
			# Warnings
			# overheat <0.6, .8-.9, >.9
			temp_pct = maxtmpstream()
			if ((temp_pct<0.6) and (overheat!=0)):
				overheat = 0
				myserwrite(b"LG12=1\nLR12=0\n")
			if ((temp_pct>=0.6) and (temp_pct<0.8) and (overheat!=1)):
				overheat = 1
				myserwrite(b"LG12=0\nLR12=1\n")
			if ((temp_pct>=0.8) and (overheat!=2)):
				overheat = 2
				myserwrite(b"LG12=0\nLR12=3\n")
#      print("Max heat: "+str(round(temp_pct*100,0))+" gegiservice:"+str(krpcgegi)+" time="+str(time.time()-lasttemptime))
			lasttemptime = time.time()
			# power
			rmax = resourceelectricmaxstream()
			if rmax>0:
				power_pct = resourceelectriccurstream()/rmax
			if (abs(power_pct-lastpowerpct)>0.01):
				lastpowerpct = power_pct
				powercommand = "A1="+str(int(power_pct*255))+"\n"
				myserwrite(powercommand.encode())
			if ((power_pct>=.2) and (lowpower!=0)):
				lowpower = 0
				myserwrite(b"LG11=1\nLR11=0\n")
			if ((power_pct<.2) and (power_pct>.1) and (lowpower!=1)):
				lowpower = 1
				myserwrite(b"LG11=0\nLR11=1\n")
			if ((power_pct<=.1) and (lowpower!=2)):
				lowpower = 2
				myserwrite(b"LG11=0\nLR11=3\n")
			# fuel
			rmax = resourceliquidfuelmaxstream()
			if rmax>0:
				fuel_pct = resourceliquidfuelcurstream()/rmax
			if (((fuel_pct>=.2) or (fuel_pct==0)) and (lowfuel!=0)):
				lowfuel = 0
				myserwrite(b"LG10=1\nLR10=0\n")
			if ((fuel_pct<.2) and (fuel_pct>.1) and (lowfuel!=1)):
				lowfuel = 1
				myserwrite(b"LG10=0\nLR10=1\n")
			if ((fuel_pct<=.1) and (fuel_pct>0) and (lowfuel!=2)):
				lowfuel = 2
				myserwrite(b"LG10=0\nLR10=3\n")

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

  # is kRPCGegi supported?
	try:
		print("Checking for kRPC Gegi service\n")
		check = conn.gegi.active_gegi.max_temp_pct()
	except AttributeError:
		sys.exit("kRPC GEGI service not available. Make sure that kRPCGegi.dll is in GameData/kRPC directory")
	print("kRPC Gegi available\n")

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
			except ConnectionResetError:
				myserwrite("P0=Connection\nP1=closed\n".encode())
				ser.close()
				sys.exit("Connection closed")

if __name__ == '__main__':
    main()
