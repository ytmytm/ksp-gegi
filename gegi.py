import krpc
import time
import serial
from si_prefix import si_format
from time_format import time_format

ser=serial.Serial(port="COM21",baudrate=115200,timeout=0,write_timeout=0)

if not ser.isOpen():
	print("Can't open serial port!")

lastflush = time.time()
serbuffer = b"\n"

def myserwrite(line):
	global serbuffer
	serbuffer = serbuffer+line

def myserflush():
	global lastflush
	global serbuffer
	print("Flush!"+str(round((time.time()-lastflush)*1000))+"\t")
	lastflush = time.time()
	ser.write(serbuffer)
#	print(str(serbuffer))
	serbuffer = b"\n"
	ser.flush()

conn = None
while conn==None:
	try:
		conn = krpc.connect(name='Arduino')
	except (krpc.error.NetworkError,ConnectionRefusedError):
		print("Connection refused, waiting 5s")
		myserwrite("P1=Connecting...\n".encode)
		time.sleep(5)

print("Connection successful "+conn.krpc.get_status().version)

vessel = None
while vessel==None:
	try:
		vessel = conn.space_center.active_vessel
	except krpc.error.RPCError:
		print("Not in proper game scene")
		myserwrite("P0=Waiting for\nP1=game scene\n".encode)
		time.sleep(1)

print("Active vessel:"+vessel.name)
line = "P0="+conn.krpc.get_status().version+"\n"
line = line+"P1="+vessel.name+"\n"
myserwrite(line.encode())
time.sleep(1)

# ask for status
myserwrite(b"R\n")

control = vessel.control
#refframe = vessel.orbit.body.reference_frame
#refframe = vessel.orbit.body.non_rotating_reference_frame
flight   = conn.add_stream(vessel.flight,vessel.orbit.body.reference_frame)
speed	 = conn.add_stream(vessel.flight,vessel.orbit.body.non_rotating_reference_frame)
orbit	 = vessel.orbit

lastrcs = control.rcs
lastsas = control.sas
lastgear = control.gear
lastlights = control.lights
lastgforce = -100
lastpowerpct = -100
stageabort = False
overheat = 3
lowpower = 3
lowfuel = 3
lcdmode = 0

# may throw krpc.error.RPCError if vessel no longer active/exists,
# should roll back to vessel = conn.space_center.active_vessel above loop
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

	try:
		temp_pct=max([max(part.temperature/part.max_temperature,part.skin_temperature/part.max_skin_temperature) for part in vessel.parts.all])
	except ValueError:
		temp_pct = 0
	res = vessel.resources
	rmax = res.max('ElectricCharge')
	if rmax>0:
		power_pct = res.amount('ElectricCharge')/rmax
	else:
		power_pct = 0
	rmax = res.max('LiquidFuel')
	if rmax>0:
		fuel_pct = res.amount('LiquidFuel')/rmax
	else:
		fuel_pct = 0
#	print("Max heat: "+str(round(temp_pct*100,0))+"\tPower: "+str(round(power_pct*100,0))+"\tL.fuel: "+str(round(fuel_pct*100,0)))

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
				lastpowerpct=-100
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
		# g-force changed enough?
		newgforce = vessel.flight().g_force
		if (abs(newgforce-lastgforce)>0.01):
			lastgforce = newgforce
			newgforce = min(abs(newgforce),5)
			newgforce = int(newgforce*255/5)
			gforcecommand = "A0="+str(newgforce)+"\n"
			myserwrite(gforcecommand.encode())
		# LCD
		if lcdmode==0: # switch on middle = Orbit
			val = orbit.apoapsis_altitude
			if val>=0:
				fval = si_format(val, precision=2).rjust(7)[:7]+" "
			else:
				fval = si_format(val, precision=2).rjust(8)[:8]
			line = "P0=A:"+fval+time_format(orbit.time_to_apoapsis)+"\n"
			val = orbit.periapsis_altitude
			if val>=0:
				fval = si_format(val, precision=2).rjust(7)[:7]+" "
			else:
				fval = si_format(val, precision=2).rjust(8)[:8]
			line = line+"P1=P:"+fval+time_format(orbit.time_to_periapsis)+"\n"
		elif lcdmode==1: # switch on right = Landing Altitude+Speed
			fval = si_format(flight().surface_altitude, precision=3).rjust(8)[:8]
			line = "P0=ALT:"+fval+"m\nP1=V"+chr(126)
			ss = flight().speed
			vs = flight().vertical_speed
			fval = si_format(abs((ss*ss-vs*vs)**(1/2)), precision=0).rjust(4)[:4]
			line = line+fval+" v"
			fval = si_format(abs(vs), precision=0).rjust(5)[:5]
			line = line+fval+"m/s\n"
		elif lcdmode==2: # switch on left = Target(?)
			line="P0=Mode 1 Left\nP1=Target mode\n"
		#print("mode"+str(lcdmode)+" "+line)
		myserwrite(line.encode())
		# Warnings
		# overheat <0.6, .8-.9, >.9
		if ((temp_pct<0.6) and (overheat!=0)):
			overheat = 0
			myserwrite(b"LG12=1\n")
			myserwrite(b"LR12=0\n")
		if ((temp_pct>=0.6) and (temp_pct<0.8) and (overheat!=1)):
			overheat = 1
			myserwrite(b"LG12=0\n")
			myserwrite(b"LR12=1\n")
		if ((temp_pct>=0.8) and (overheat!=2)):
			overheat = 2
			myserwrite(b"LG12=0\n")
			myserwrite(b"LR12=3\n")
		# power
		if (abs(power_pct-lastpowerpct)>0.01):
			lastpowerpct=power_pct
			newpower=int(power_pct*255)
			powercommand = "A1="+str(newpower)+"\n"
			myserwrite(powercommand.encode())
		if ((power_pct>=.2) and (lowpower!=0)):
			lowpower = 0
			myserwrite(b"LG11=1\n")
			myserwrite(b"LR11=0\n")
		if ((power_pct<.2) and (power_pct>.1) and (lowpower!=1)):
			lowpower = 1
			myserwrite(b"LG11=0\n")
			myserwrite(b"LR11=1\n")
		if ((power_pct<=.1) and (lowpower!=2)):
			lowpower = 2
			myserwrite(b"LG11=0\n")
			myserwrite(b"LR11=3\n")
		# fuel
		if (((fuel_pct>=.2) or (fuel_pct==0)) and (lowfuel!=0)):
			lowfuel = 0
			myserwrite(b"LG10=1\n")
			myserwrite(b"LR10=0\n")
		if ((fuel_pct<.2) and (fuel_pct>.1) and (lowfuel!=1)):
			lowfuel = 1
			myserwrite(b"LG10=0\n")
			myserwrite(b"LR10=1\n")
		if ((fuel_pct<=.1) and (fuel_pct>0) and (lowfuel!=2)):
			lowpower = 2
			myserwrite(b"LG10=0\n")
			myserwrite(b"LR10=3\n")

		# serial state change
		if control.rcs!=lastrcs:
			lastrcs = control.rcs
			if lastrcs:
				myserwrite(b"LG6=1\n")
				myserwrite(b"LR6=0\n")
			else:
				myserwrite(b"LG6=0\n")
				myserwrite(b"LR6=1\n")
		if control.sas!=lastsas:
			lastsas = control.sas
			if lastsas:
				myserwrite(b"LG7=1\n")
				myserwrite(b"LR7=0\n")
			else:
				myserwrite(b"LG7=0\n")
				myserwrite(b"LR7=1\n")
		if control.gear!=lastgear:
			lastgear = control.gear
			if lastgear:
				myserwrite(b"LG5=1\n")
				myserwrite(b"LR5=0\n")
			else:
				myserwrite(b"LG5=0\n")
				myserwrite(b"LR5=1\n")
		if control.lights!=lastlights:
			lastlights = control.lights
			if lastlights:
				myserwrite(b"LG4=1\n")
				myserwrite(b"LR4=0\n")
			else:
				myserwrite(b"LG4=0\n")
				myserwrite(b"LR4=1\n")
	myserflush()
#	time.sleep(.1)
