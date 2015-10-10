import krpc
import time
from msvcrt import kbhit,getch

conn = None
while conn==None:
	try:
		conn = krpc.connect(name='Arduino')
	except (krpc.error.NetworkError,ConnectionRefusedError):
		print("Connection refused, waiting 5s")
		time.sleep(5)

print("Connection successful "+conn.krpc.get_status().version)

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
			
	time.sleep(1)
