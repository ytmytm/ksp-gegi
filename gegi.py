import krpc
import time
import serial
from msvcrt import kbhit,getch

conn = None
while conn==None:
	try:
		conn = krpc.connect(name='Arduino')
	except (krpc.error.NetworkError,ConnectionRefusedError):
		print("Connection refused, waiting 5s")
		time.sleep(5)

print("Connection successful "+conn.krpc.get_status().version)

ser=serial.Serial("COM3",9600,timeout=0.2)
if not ser.isOpen():
	print("Can't open COM7!")

vessel = None
while vessel==None:
	try:
		vessel = conn.space_center.active_vessel
	except krpc.error.RPCError:
		print("Not in proper game scene")
		time.sleep(1)
		
print("Active vessel:"+vessel.name)

control = vessel.control
#refframe = vessel.orbit.body.reference_frame
#refframe = vessel.orbit.body.non_rotating_reference_frame
flight   = conn.add_stream(vessel.flight,vessel.orbit.body.reference_frame)
speed	 = conn.add_stream(vessel.flight,vessel.orbit.body.non_rotating_reference_frame)
orbit	 = vessel.orbit

lastrcs = control.rcs
lastsas = control.sas
lastgear = control.gear
lastgforce = -100
overheat = 0
lowpower = 0
lowfuel = 0

# may throw krpc.error.RPCError if vessel no longer active/exists,
# should roll back to vessel = conn.space_center.active_vessel above loop
while True:
	print("---------CONTROL")
	print("SAS:"+str(control.sas)+"\tRCS:"+str(control.rcs))
	print("Gear:"+str(control.gear)+"\tLights:"+str(control.lights))
	print("Throttle:"+str(control.throttle))
	print("---------ORBIT")
	print("Speed:"+str(round(orbit.speed,2)))
	print("Apoapsis:"+str(round(orbit.apoapsis_altitude,0))+"\tPeriapsis:"+str(round(orbit.periapsis_altitude,0)))
	print("Time to:"+str(round(orbit.time_to_apoapsis,0))+" s\tTime to:  "+str(round(orbit.time_to_periapsis,0))+" s")
	print("---------FLIGHT")
	print("Altitude: "+str(round(flight().mean_altitude,0))+"\tSpeed: "+str(round(speed().speed,2)))
	print("Pitch :"+str(round(flight().pitch,1))+"\tRoll :"+str(round(flight().roll,1))+"\t Head :"+str(round(flight().heading,1)))

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
	print("Max heat: "+str(round(temp_pct*100,0))+"\tPower: "+str(round(power_pct*100,0))+"\tL.fuel: "+str(round(fuel_pct*100,0)))

	# serial link
	if ser.isOpen():
		line = "?"
		while len(line)>0:
			line = ser.readline().decode("utf-8").rstrip()
			print("Serial:["+line+"]\n----\n")
			if line=="I":
				lastrcs=None
				lastsas=None
				lastgear=None
				lastgforce=-100
			if line[:3]=="P0=":
				control.throttle = int(line[3:],16)/255
			if line[:3]=="P1=":
				# timewarp
				newtimewarp = min(int(line[3:],16)/255/0.9,1)
				railslevel = int(newtimewarp*7)
				physlevel = int(newtimewarp*4)
				print("warp:"+str(newtimewarp)+"\tphys:"+str(physlevel)+"\trail"+str(railslevel))
				if (conn.space_center.warp_mode == conn.space_center.WarpMode.rails):
					conn.space_center.rails_warp_factor = railslevel
				elif (conn.space_center.warp_mode == conn.space_center.WarpMode.physics):
					conn.space_center.physics_warp_factor = physlevel
				else:
				# no time warp - try to set as rails, if failed then try to set as physics
					conn.space_center.rails_warp_factor = railslevel
					if (conn.space_center.warp_mode != conn.space_center.WarpMode.rails):
						conn.space_center.physics_warp_factor = physlevel
			if line=="D0=1":
				control.activate_next_stage()
			if line=="D1=0":
				control.rcs=False
			if line=="D1=1":
				control.rcs=True
			if line=="D2=0":
				control.sas=False
			if line=="D2=1":
				control.sas=True
			if line=="D3=0":
				control.gear=False
			if line=="D3=1":
				control.gear=True

		# Status
		# g-force changed enough?
		newgforce = vessel.flight().g_force
		if (abs(newgforce-lastgforce)>0.01):
			lastgforce = newgforce
			newgforce = min(abs(newgforce),5)
			newgforce = int(newgforce*255/5)
			gforcecommand = "A0="+str(newgforce)+"\n"
			print(gforcecommand)
			ser.write(gforcecommand.encode())

		# Warnings
		# overheat <0.6, .8-.9, >.9
		if ((temp_pct<0.6) and (overheat!=0)):
			overheat = 0
			ser.write(b"LG4=1\n")
			ser.write(b"LR4=0\n")
		if ((temp_pct>=0.6) and (temp_pct<0.8) and (overheat!=1)):
			overheat = 1
			ser.write(b"LG4=0\n")
			ser.write(b"LR4=1\n")
		if ((temp_pct>=0.8) and (overheat!=2)):
			overheat = 2
			ser.write(b"LG4=0\n")
			ser.write(b"LR4=2\n")
		# power
		if ((power_pct>=.2) and (lowpower!=0)):
			lowpower = 0
			ser.write(b"LG5=1\n")
			ser.write(b"LR5=0\n")
		if ((power_pct<.2) and (power_pct>.1) and (lowpower!=1)):
			lowpower = 1
			ser.write(b"LG5=0\n")
			ser.write(b"LR5=1\n")
		if ((power_pct<=.1) and (lowpower!=2)):
			lowpower = 2
			ser.write(b"LG5=0\n")
			ser.write(b"LR5=2\n")
		# fuel
		if (((fuel_pct>=.2) or (fuel_pct==0)) and (lowfuel!=0)):
			lowfuel = 0
			ser.write(b"LG6=1\n")
			ser.write(b"LR6=0\n")
		if ((fuel_pct<.2) and (fuel_pct>.1) and (lowfuel!=1)):
			lowfuel = 1
			ser.write(b"LG6=0\n")
			ser.write(b"LR6=1\n")
		if ((fuel_pct<=.1) and (fuel_pct>0) and (lowfuel!=2)):
			lowpower = 2
			ser.write(b"LG6=0\n")
			ser.write(b"LR6=2\n")

		# serial state change
		if control.rcs!=lastrcs:
			lastrcs = control.rcs
			if lastrcs:
				ser.write(b"LG1=1\n")
				ser.write(b"LR1=0\n")
			else:
				ser.write(b"LG1=0\n")
				ser.write(b"LR1=1\n")
		if control.sas!=lastsas:
			lastsas = control.sas
			if lastsas:
				ser.write(b"LG2=1\n")
				ser.write(b"LR2=0\n")
			else:
				ser.write(b"LG2=0\n")
				ser.write(b"LR2=1\n")
		if control.gear!=lastgear:
			lastgear = control.gear
			if lastgear:
				ser.write(b"LG3=1\n")
				ser.write(b"LR3=0\n")
			else:
				ser.write(b"LG3=0\n")
				ser.write(b"LR3=1\n")

	# local console
	if kbhit():
		k = ord(getch())
		if k == 13:
			control.activate_next_stage()
		if k == ord('s'):
			control.sas = not control.sas
		if k == ord('r'):
			control.rcs = not control.rcs
		if k == ord('g'):
			control.gear = not control.gear
		if k == ord('l'):
			control.lights = not control.lights
		if k == ord('b'):
			control.brakes = not control.brakes
		if k == ord('0'):
			control.throttle = 0
		if (k>48) and (k<=57):
			control.throttle = (k-48)/10
			
	#time.sleep(1)
