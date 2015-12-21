
#include <Arduino.h>
#include <Wire.h>
// https://bitbucket.org/fmalpartida/new-liquidcrystal/downloads
#include <LiquidCrystal_I2C.h> // Using version 1.2.1

// IDE: Arduino/Genuino Micro

// potencjometr: niebieski z czarną kreską do GND, biały do +5V, niebieski do pinu A0 / A1
// LCD: SDA->2, SCL->3

class analogOutPin {
  public:
    analogOutPin(const uint8_t id, const uint8_t pin);
    void updateState(const uint8_t val) const ;
    const uint8_t getId() const { return(m_id); }
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

void setup() {
  // initialize serial communications
  Serial.begin(SERIAL_SPEED);
  Serial1.begin(SERIAL_SPEED);
  // wait for USB device
  while (!Serial);
  // set timeout to 200ms
  Serial.setTimeout(200);
  // start blink counter
  lcd.begin(16,2);   // initialize the lcd for 16 chars 2 lines, turn on backlight
  lcd.setCursor(0,0);
  lcd.print("KSP-Gegi");
  lcd.setCursor(0,1);
  lcd.print("Ready for action");
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
	}
}

void loop() {
  checkSerialInputUSBtoUART();
  checkSerialInputUARTtoUSB();
  // send joystick state
  delay(200);
}

