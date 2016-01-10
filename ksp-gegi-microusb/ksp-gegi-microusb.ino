
#include <Arduino.h>
#include <Wire.h>
// https://bitbucket.org/fmalpartida/new-liquidcrystal/downloads
#include <LiquidCrystal_I2C.h> // Using version 1.2.1
// https://github.com/MHeironimus/ArduinoJoystickLibrary
#include <Joystick.h>
#include "U8glib.h"

U8GLIB_SSD1306_128X64_2X u8g(U8G_I2C_OPT_DEV_0|U8G_I2C_OPT_NO_ACK|U8G_I2C_OPT_FAST); // more RAM used, FAST transfer

// IDE: Arduino/Genuino Micro

// potencjometr: niebieski z czarną kreską do GND, biały do +5V, niebieski do pinu A0 / A1
// LCD: SDA->2, SCL->3

// Stage/Abort status (on=stage, off=abort)
uint8_t stageabort = 1;
// joy1 switch status - change meaning of joy2 axes (X:on=rotate, off=axis; Y:on=hatswitch#0, off=rudder)
uint8_t joy1switch = 0;
// joy2 switch status - change meaning of joy1 axes (X:on=rotate, off=axis; Y:on=rotate, off=axis)
uint8_t joy2switch = 0;

bool testMode = true;	// in test mode we can blink lights without Python!

// almost copy from ksp-gegi-mini!

// used from within digitalPin class (not nice, I know!)
void handleSlaveButton(const uint8_t id, const uint8_t state);

class digitalPin {
  public:
    digitalPin(const uint8_t id, const uint8_t pinSwitch);
    void updateSwitch(const bool force);
    uint8_t getId() { return(m_id); }
    uint8_t getSwitchState() const { return(m_lastPinState); }
  private:
    const uint8_t m_id, m_pinSwitch;
    uint8_t m_lastPinState { HIGH } ;
};

digitalPin digiPins[] = {
  digitalPin(10,5),    // joy1switch
  digitalPin(11,7)	   // joy2switch
};

digitalPin::digitalPin(const uint8_t id, const uint8_t pinSwitch) :
  m_id(id), m_pinSwitch(pinSwitch)
{
  if (m_pinSwitch>0) {
    pinMode(m_pinSwitch,INPUT_PULLUP);
  }
}

void digitalPin::updateSwitch(const bool force) {
  if (m_pinSwitch>0) {
    // reverse logic because switches are connected to GND with internal pullup, so pushed state (ON) is 0V
    uint8_t state = !digitalRead(m_pinSwitch);
    if (force || (state!=m_lastPinState)) {
      Serial.write('D');
      Serial.print(m_id);
      Serial.write('=');
      Serial.println(state);
      m_lastPinState = state;
      // map to joystick events
      handleSlaveButton(m_id,m_lastPinState);
    }
  }
}

/////////////

class analogInPin {
  public:
    analogInPin(const uint8_t id, const uint8_t pin, const int threshold);
    void update(const bool force);
    uint8_t getAValue() const;
  private:
    void updateJoystick() const;
    const uint8_t m_id, m_pin;
    const int m_threshold;
    int m_lastAValue { 0 };
    int m_lastRValue { 0 };
};

analogInPin analogInPins[] = {
  analogInPin(0,A6,2),  // throttle
  analogInPin(1,A8,5),	// timewarp
  analogInPin(2,A1,2),	// joy1x
  analogInPin(3,A0,2),	// joy1y
  analogInPin(4,A3,2),	// joy2x
  analogInPin(5,A2,2),	// joy2y
};

analogInPin::analogInPin(const uint8_t id, const uint8_t pin, const int threshold) :
	m_id(id), m_pin(pin), m_threshold(threshold)
{
}

void analogInPin::update(const bool force) {
	// map to the range of the analog out
	m_lastRValue = analogRead(m_pin);
	int aValue = map(m_lastRValue, 0, 1023, 0, 255);
	// is it different enough from the last reading?
	if (force || abs(aValue-m_lastAValue)>m_threshold) {
		if (aValue<m_threshold) {
			aValue = 0;
		}
		if (aValue>255-m_threshold) {
			aValue = 255;
		}
		// dump status
		Serial.print("P");
		Serial.print(m_id);
		Serial.print("=");
		Serial.println(aValue,HEX);
		m_lastAValue = aValue;
		// map to joystick events
		updateJoystick();
	}
}

uint8_t analogInPin::getAValue(void) const {
	return (m_lastAValue);
}

void analogInPin::updateJoystick() const {
	switch (m_id) {
		case 0: // throttle pot
			Joystick.setThrottle(m_lastAValue);
			break;
		case 2:	// joy1x X on: rotation, off: axis
			if (joy2switch) {
				Joystick.setXAxisRotation(map(m_lastRValue, 0, 1023, 0, 359));
			} else {
				Joystick.setXAxis(m_lastAValue-127);
			}
			break;
		case 3: // joy1y Y on: rotation, off: axis
			if (joy2switch) {
				Joystick.setYAxisRotation(map(m_lastRValue, 0, 1023, 0, 359));
			} else {
				Joystick.setYAxis(m_lastAValue-127);
			}
			break;
		case 4: // joy2x Z on: rotation, off: axis
			if (joy1switch) {
				Joystick.setZAxisRotation(map(m_lastRValue, 0, 1023, 0, 359));
			} else {
				Joystick.setZAxis(m_lastAValue-127);
			}
			break;
		case 5: // joy2y on: ignore, off: rudder
			if (joy1switch) {
			} else {
				Joystick.setRudder(m_lastAValue);
			}
			break;
	}
}

class analogOutPin {
  public:
    analogOutPin(const uint8_t id, const uint8_t pin);
    void updateState(const uint8_t val) const ;
    const uint8_t getId() { return(m_id); }
  private:
    const uint8_t m_id, m_pin;
};

analogOutPin::analogOutPin(const uint8_t id, const uint8_t pin) :
	m_id(id), m_pin(pin)
{
}

void analogOutPin::updateState(const uint8_t val) const {
  analogWrite(m_pin,val);
}

analogOutPin analogOutPins[] = {
  analogOutPin(0,9),	// g-force
  analogOutPin(1,10)    // electrical power
};

// Set the pins on the I2C chip used for LCD connections:
//                    addr, en,rw,rs,d4,d5,d6,d7,bl,blpol
LiquidCrystal_I2C lcd(0x3f, 2, 1, 0, 4, 5, 6, 7, 3, POSITIVE);

// serial port
#define SERIAL_SPEED 115200

// used below
void oledRedraw();

void setup() {
  // initialize serial communications
  Serial.begin(SERIAL_SPEED);
  Serial1.begin(SERIAL_SPEED);
  // don't wait for USB device, we don't care if port has been opened
  // while (!Serial);
  // set timeout to 200ms
  Serial.setTimeout(200);
  lcd.begin(16,2);   // initialize the lcd for 16 chars 2 lines, turn on backlight
  lcd.setCursor(0,0);
  lcd.print("KSP-Gegi");
  lcd.setCursor(0,1);
  lcd.print("Ready for action");
  // joystick setup
  Joystick.begin(true);	// do auto send state
  // show something on OLED
  oledRedraw();
  // request status update
  Serial.println("I");
}

// commands like ^A{id}={val}$
void handleSerialInputAnalogOut() {
  const uint8_t id = Serial.parseInt();  // skip '='
  const uint8_t val = Serial.parseInt(); // skip newline
//  Serial.print(id); Serial.write(' '); Serial.println(val);
  for (auto &p : analogOutPins) {
    if (p.getId()==id) {
      p.updateState(val);
    }
  }
}

// commands like ^P{line:0,1}={text0..15}$ (consume all characters until end of the line)
void handleSerialInputLCD() {
  uint8_t i=0, c;
  const uint8_t id = Serial.parseInt();
  Serial.read(); // skip '='
//  Serial.print("LCDin"); Serial.println(id);
  if (id==0 || id==1) {
    lcd.setCursor(0,id);
    c = -1;
    while (c!='\r' && c!='\n') {
      if (Serial.available()>0) {
        c = Serial.read();
      } else {
        c = -1;
      }
      if (c>0 && c!='\r' && c!='\n' && i<16) {
        i++;
        lcd.write(c);
//        Serial.print(c,HEX);
      }
    }
    for (;i<16;i++) {
      lcd.write(' ');
    }
//    Serial.println("endLCD");
  }
}

#define OLEDBUFSIZE 512
// initialization stuff
uint8_t oledBuf[OLEDBUFSIZE+1] = { 0x01,0x00,0x20,0x4b,0x53,0x50,0x2d,0x47,0x65,0x67,0x69,0x00,
  0x01,0x00,0x30,0x52,0x65,0x61,0x64,0x79,0x20,0x66,0x6F,0x72,0x20,0x61,0x63,0x74,0x69,0x6F,0x6E,0x00,
  7,128,0,0,15,7,128,0,32,15,7,128,0,64,15,
  7,128,64,0,49,7,128,64,32,49,7,128,64,64,49,
  0x00 };

// OLED commands
#define OLED_DRAW_STOP  0
#define OLED_DRAW_STR   1 // followed by x y string\, like "Line2\"
#define OLED_DRAW_BOX   2 // followed by x y width height
#define OLED_DRAW_FRAME 3 // followed by x y width height
#define OLED_DRAW_PIXEL 4 // followed by x y
#define OLED_DRAW_HLINE 5 // followed by x y width
#define OLED_DRAW_VLINE 6 // followed by x y height
#define OLED_DRAW_LINE  7 // followed by x1 y1 x2 y2
#define OLED_DRAW_CIRCLE 8 // followed by x y radius

void drawOLED(void) {
  // graphic commands to redraw the complete screen should be placed here
  u8g.setFont(u8g_font_unifontr); // reduced font, only glyphs 0x20-0x7f
  uint16_t i=0;
  uint8_t cmd, x, y, w, h, x2, y2, radius;
  while ((i<OLEDBUFSIZE) && oledBuf[i]!=0) {
    cmd = oledBuf[i++];
    if (OLED_DRAW_STOP==cmd) break; // stop immediately if commanded
    x=oledBuf[i++]; y=oledBuf[i++];
//    Serial.print("cmd"); Serial.print(cmd); Serial.print(" x="); Serial.print(x); Serial.print(" y="); Serial.println(y);
    switch(cmd) {
        case OLED_DRAW_STR:
//          Serial.print("["); Serial.print((const char*)&oledBuf[i]); Serial.println("]");
          u8g.drawStr(x,y,(const char*)&oledBuf[i]);
          // skip to the end of string;
          while (i<OLEDBUFSIZE && oledBuf[i]!=0) {
            i++;
          }
          i++; // skip past ending 0
          break;
        case OLED_DRAW_BOX:
          w = oledBuf[i++]; h = oledBuf[i++];
//          Serial.print("w="); Serial.print(w); Serial.print(" h="); Serial.println(h);
          u8g.drawBox(x,y,w,h);
          break;
        case OLED_DRAW_FRAME:
          w = oledBuf[i++]; h = oledBuf[i++];
//          Serial.print("w="); Serial.print(w); Serial.print(" h="); Serial.println(h);
          u8g.drawFrame(x,y,w,h);
          break;
        case OLED_DRAW_PIXEL:
          u8g.drawPixel(x,y);
          break;
        case OLED_DRAW_HLINE:
          w = oledBuf[i++];
//          Serial.print("w="); Serial.println(w);
          u8g.drawHLine(x,y,w);
          break;
        case OLED_DRAW_VLINE:
          h = oledBuf[i++];
//          Serial.print("h="); Serial.println(h);
          u8g.drawVLine(x,y,h);
          break;
        case OLED_DRAW_LINE:
          x2 = oledBuf[i++]; y2 = oledBuf[i++];
//          Serial.print("x2="); Serial.print(x2); Serial.print(" y2="); Serial.println(y2);
          u8g.drawLine(x,y,x2,y2);
          break;
        case OLED_DRAW_CIRCLE:
          radius = oledBuf[i++];
//          Serial.print("rad="); Serial.println(radius);
          u8g.drawCircle(x,y,radius);
          break;
    }
  }
}

// read a string of gfx commands and keep them in a buffer so drawOLED() can use them
void handleSerialInputOLED() {
  uint16_t i=0;
  uint8_t cmd, c;
//  Serial.println("OLEDstart");
  while ((i<OLEDBUFSIZE) && (Serial.available()>0) && (Serial.peek()!= '\n')) {
    cmd = Serial.parseInt();
    oledBuf[i++] = cmd;
    oledBuf[i++] = Serial.parseInt(); // x
    oledBuf[i++] = Serial.parseInt(); // y
    switch(cmd) {
        case OLED_DRAW_STR:
          Serial.read();  // skip separator
          while (i<OLEDBUFSIZE) {
            while (Serial.available()==0) { };
            c = Serial.read();
            if (c == '\\') break; // end marker
            oledBuf[i++] = c;
          }
          oledBuf[i++] = '\0'; // string terminator
          break;
        case OLED_DRAW_BOX:
        case OLED_DRAW_FRAME:
        case OLED_DRAW_LINE:
          oledBuf[i++] = Serial.parseInt(); // read two more bytes (one here, one below)
        case OLED_DRAW_HLINE:
        case OLED_DRAW_VLINE:
        case OLED_DRAW_CIRCLE:
          oledBuf[i++] = Serial.parseInt(); // read one more byte
        case OLED_DRAW_STOP:
        case OLED_DRAW_PIXEL:
          break;
    }
  }
  oledBuf[i]=0; // command string terminator
//  Serial.println("OLEDredraw");
  oledRedraw();
//  Serial.println("OLEDend");
}

void oledRedraw() {
  // redraw screen
  u8g.firstPage();
  do {
    drawOLED();
  } while( u8g.nextPage() );
}

// called after UART slave reports button press/release
// map switch IDs to joystick buttons
void handleSlaveButton(const uint8_t id, const uint8_t state) {
	// handle stage switch
	uint8_t buttonId = 0x80;
	switch (id) {
		case 4:
			buttonId = 5;
			break;
		case 5:
			buttonId = 4;
			break;
		case 6:
			buttonId = 2;
			break;
		case 7:
			buttonId = 3;
			break;
		case 8:
			buttonId = stageabort ? 1 : 0;
			break;
		case 9:
			stageabort = state;	// on=abort, off=stage
			break;
    case 10:
      buttonId = 6;
      break;
    case 11:
      buttonId = 7;
      break;
  }
//Serial.print("id,state,buttonid,stageabort="); Serial.print(id); Serial.write(' '); Serial.print(state); Serial.write(' '); Serial.print(buttonId); Serial.write(' '); Serial.println(stageabort);
	if (buttonId < 0x80) {
		Joystick.setButton(buttonId,state);
	}
}

void handleStatusReset() {
  // disable test mode
  testMode = false;
  // pass own status
  updatePins(true);
  updateAnalogs(true);
  // ask slave to update status
  Serial1.println("R");
  // request status update
  Serial.println("I");
}

// pass data from USB host (PC) to UART
// - handle own devices (consume this data)
// - pass everything else to mini slave
void checkSerialInputUSBtoUART() {
  uint8_t c;
  while (Serial.available()) {
    c = Serial.read();
    if (c == 'A') {
      handleSerialInputAnalogOut();
    }
    else if (c == 'P') {
      handleSerialInputLCD();
    }
    else if (c == 'O') {
      handleSerialInputOLED();
    }
    else if ((c == 'R') & (Serial.peek()=='\n')) {
      handleStatusReset();
    }
	  else {
      Serial1.write(c);
	  }
  }
}

// pass data from UART slave (mini) to USB host (PC)
// - convert some button presses to joystick events
// - pass everyting else
void checkSerialInputUARTtoUSB() {
  uint8_t c;
  while (Serial1.available()) {
		c = Serial1.read();
		Serial.write(c);
		if (c == 'D') {
			const uint8_t id = Serial1.parseInt();  // skip '='
			const uint8_t state = Serial1.parseInt(); // skip newline
			Serial.print(id);
			Serial.write('=');
			Serial.println(state);
			handleSlaveButton(id,state);
		}
	}
}

void updateAnalogs(const bool force) {
  for (auto &p : analogInPins) {
    p.update(force);
  }
}

void updatePins(const bool force) {
  for (auto &p : digiPins) {
    p.updateSwitch(force);
    // remember state so analog axes are updated accordingly
    if (p.getId()==10) {
        joy1switch = p.getSwitchState();
    }
    if (p.getId()==11) {
        joy2switch = p.getSwitchState();
    }
  }
}

void handleTestMode() {
	analogOutPins[0].updateState(analogInPins[0].getAValue());
	analogOutPins[1].updateState(analogInPins[1].getAValue());
}

void loop() {
  checkSerialInputUSBtoUART();
  checkSerialInputUARTtoUSB();
  updatePins(false);
  updateAnalogs(false);
  if (testMode) {
	  handleTestMode();
  }
}
