KSP Gegi - Kerbal Space Program Status and Control Panel
========================================================

This is the source code repository for the KSP Gegi project.

For more details please go to [KSP Gegi project page on hackaday.io](https://hackaday.io/project/8891-ksp-gegi)

# kRPCGegi

This extension can be compiled using Visual Studio or Xamarin Studio.

Move
```
kRPCGegi\kRPCGegi\bin\Release\kRPCGegi.dll
```
to GameData of your KSP installation

# Gegi.py

Just copy all .py files somewhere and run gegi.py in python 3.

Before connecting to localhost kRPC server it will ask you for serial port (COM), to which control panel is attached.

# Without Python

Control panel also works without actually running gegi.py or krpc. The joysticks and some of the buttons are mapped to
USB game controllers that you can set up in in-game Input menu.
