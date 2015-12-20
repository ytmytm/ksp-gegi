
#include <Arduino.h>
#include <Wire.h>
// https://bitbucket.org/fmalpartida/new-liquidcrystal/downloads
#include <LiquidCrystal_I2C.h> // Using version 1.2.1

// dł kabelków 15-20cm
// diody LED: niebieskie (bez rezystora, krótka nóżka) do GND, białe (z rezystorem, długa nóżka) do pinu
// potencjometr: niebieski z czarną kreską do GND, biały do +5V, niebieski do pinu A0 / A1
// przełączniki2: niebieski do GND, biały do pinu, wszystkie zamontowane tak, aby niebieski był w środku, biały na dole, a niepodłączone u góry (wtedy gałka w górę==załączenie)
// przełączniki3: środkowy (ciemny) do GND, boczne do pinów
// LCD: SDA->A4, SCL->A5

class digitalPin {
  public:
    digitalPin(const uint8_t id, const uint8_t pinSwitch, const uint8_t pinOn, const uint8_t pinOff);
    void updateSwitch();
    void updateLedState(const uint8_t c, const uint8_t val);
    void updateLed(const bool blink) const ;
    const uint8_t getId() const { return(m_id); }
  private:
    const uint8_t m_id, m_pinSwitch, m_pinOn, m_pinOff;
    uint8_t m_lastPinState { HIGH } ;
    uint8_t m_lastLedState { 0 } ; // bits: 0=GxON, 1=RxON, 2=GxBLINK, 3=RxBLINK
};

digitalPin digiPins[] = {
  digitalPin(0,4,0,0),    // stage (id, pin switch, pin green LED (on), pin red LED (off)
  digitalPin(1,5,13,0),   // RCS
  digitalPin(2,8,9,0),    // SAS
  digitalPin(3,12,0,0),   // gear
  digitalPin(4,0,0,6),    // overheat
  digitalPin(5,0,0,7),    // low power
  digitalPin(6,0,0,3)     // low fuel
};

digitalPin::digitalPin(const uint8_t id, const uint8_t pinSwitch, const uint8_t pinOn, const uint8_t pinOff) :
  m_id(id), m_pinSwitch(pinSwitch), m_pinOn(pinOn), m_pinOff(pinOff)
{
  if (m_pinSwitch>0) {
    pinMode(m_pinSwitch,INPUT_PULLUP);
  }
  if (m_pinOn>0) {
    pinMode(m_pinOn,OUTPUT);
    digitalWrite(m_pinOn,LOW);
  }
  if (m_pinOff>0) {
    pinMode(m_pinOff,OUTPUT);
    digitalWrite(m_pinOff,LOW);
  }
}

void digitalPin::updateSwitch() {
  if (m_pinSwitch>0) {
    // reverse logic because switches are connected to GND with internal pullup, so pushed state (ON) is 0V
    uint8_t state = !digitalRead(m_pinSwitch);
    if (state!=m_lastPinState) {
      Serial.print('D');
      Serial.print(m_id);
      Serial.print('=');
      Serial.println(state);
      m_lastPinState = state;
    }
  }
}

void digitalPin::updateLedState(uint8_t c, uint8_t val) {
  uint8_t nval = m_lastLedState;
  val = val & 0b00001111;
  if (c=='G') {
    nval = nval & 0b11110000;
    nval = nval | val;
  }
  if (c=='R') {
    val = val << 4;
    nval = nval & 0b00001111;
    nval = nval | val;
  }
  m_lastLedState = nval;
}

void digitalPin::updateLed(const bool blink) const {
  uint8_t nstate;
  if (m_pinOn>0) {
    nstate = (m_lastLedState & 0x01) ? HIGH : LOW;
    if (nstate==HIGH && (m_lastLedState & 0x02) && blink) {
      nstate = !digitalRead(m_pinOn);
    }
//Serial.print("L"); Serial.print(gPin); Serial.print(nstate);
    digitalWrite(m_pinOn,nstate);
  }
  if (m_pinOff>0) {
    nstate = (m_lastLedState & 0x10) ? HIGH : LOW;
    if (nstate==HIGH && (m_lastLedState & 0x20) && blink) {
      nstate = !digitalRead(m_pinOff);
    }
//Serial.print("R"); Serial.print(rPin); Serial.print(nstate);
    digitalWrite(m_pinOff,nstate);
  }
}

class analogInPin {
  public:
    analogInPin(const uint8_t id, const uint8_t pin, const int threshold);
    void update();
  private:
    const uint8_t m_id, m_pin;
    const int m_threshold;
    int m_lastAValue { 0 };
};

analogInPin analogInPins[] = {
  analogInPin(0,A0,2),  // throttle
  analogInPin(1,A1,2)	  // timewarp
};

analogInPin::analogInPin(const uint8_t id, const uint8_t pin, const int threshold) :
	m_id(id), m_pin(pin), m_threshold(threshold)
{
}

void analogInPin::update() {
	// map to the range of the analog out
	int aValue = map(analogRead(m_pin), 0, 1023, 0, 255);
	// is it different enough from the last reading?
	if (abs(aValue-m_lastAValue)>m_threshold) {
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
  }
}

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
  analogOutPin(0,10),	// g-force
  analogOutPin(0,11)  // electrical power
};

// blinker control
unsigned long lastBlink = 0;
const unsigned long blinkInterval = 500;

// Set the pins on the I2C chip used for LCD connections:
//                    addr, en,rw,rs,d4,d5,d6,d7,bl,blpol
LiquidCrystal_I2C lcd(0x3f, 2, 1, 0, 4, 5, 6, 7, 3, POSITIVE);

// serial port
#define SERIAL_SPEED 115200

void setup() {
  // initialize serial communications at 9600 bps:
  Serial.begin(SERIAL_SPEED);
  // set timeout to 200ms
  Serial.setTimeout(200);
  // request status update
  Serial.println("I");
  // start blink counter
  lastBlink = millis();
  lcd.begin(16,2);   // initialize the lcd for 16 chars 2 lines, turn on backlight
  lcd.setCursor(0,0);
  lcd.print("KSP-Gegi");
  lcd.setCursor(0,1);
  lcd.print("Ready for action");
}

void updateAnalogs() {
  for (auto &p : analogInPins) {
    p.update();
  }
}

void updatePins() {
  const unsigned long currentMillis = millis();
  bool blink = false;
  // is it time for tick?
  if (((unsigned long)(currentMillis - lastBlink) >= blinkInterval)) {
    blink = true;
    lastBlink = currentMillis;
  }
  for (auto &p : digiPins) {
    p.updateLed(blink);
    p.updateSwitch();
  }
}

// commands like: ^L{GR}{id}={val}$
// format: "^LG1=0$" turn off green led 1 (RCS), "^LR2=1$" turn off red led 2 (SCS)
void handleSerialInputLed() {
    const uint8_t c = Serial.read();
    const uint8_t id = Serial.parseInt();  // skip '='
    const uint8_t val = Serial.parseInt(); // skip newline
    for (auto &p : digiPins) {
      if (p.getId()==id) {
        p.updateLedState(c, val);
      }
//    Serial.print(c); Serial.print(id); Serial.println(val);  // echo for ack
    }
}

// commands like ^A{id}={val}$
void handleSerialInputAnalogOut() {
    const uint8_t id = Serial.parseInt();  // skip '='
    const uint8_t val = Serial.parseInt(); // skip newline
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
          //Serial.print(c,HEX);
			  }
		  }
      for (;i<16;i++) {
        lcd.write(' ');
      }
//    Serial.println("endLCD");
	}
}

void checkSerialInput() {
  if (Serial.available()>0) {
    const uint8_t c = Serial.read();
    if (c == 'L') {
	    handleSerialInputLed();
	  }
    if (c == 'A') {
	    handleSerialInputAnalogOut();
	  }
    if (c == 'P') {
	    handleSerialInputLCD();
	  }
  }
}

void loop() {
  checkSerialInput();
  updatePins();
  updateAnalogs();
  delay(100);
}

