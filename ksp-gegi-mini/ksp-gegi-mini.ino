
#include <Arduino.h>

// IDE: Arduino Mini, ATmega168

// dł kabelków 15-20cm
// diody LED z uC: niebieskie (bez rezystora, krótka nóżka) do GND, białe (z rezystorem, długa nóżka) do pinu
// przełączniki2: niebieski do GND, biały do pinu, wszystkie zamontowane tak, aby niebieski był w środku, biały na dole, a niepodłączone u góry (wtedy gałka w górę==załączenie)
// przełączniki3: środkowy (ciemny) do GND, boczne do pinów, zamontowany bokiem

// 595:
// 15=A1 SCRCK(13) // clock
// 16=A2 SERIN(3)  // data
// 17=A3 RCK(12)   // latch
// /SRCLR(8) -> +5V
// /G (9) -> GND
// VCC (2) -> +5V
// GND (19,10,11) -> GND
// /DRAINx (4,5,6,7;14,15,16,17) = GND od LEDa (LED niebieskie, bez rezystora, krótka nożka do drain; białe, z rezystorem, długa nóżka do +5V)

// UART:
// receive commands like: ^L{GR}{id}={val}$
// format: "^LG1=0$" turn off green led 1, "^LR2=1$" turn off red led 2
// bits val=0 (OFF), val=1 (ON), val=3 (ON+BLINK)

const uint8_t clockPin = A1;  // SCRCK (13)
const uint8_t dataPin  = A2;  // SERIN (3)
const uint8_t latchPin = A3;  // RCK (12)

class digitalPin {
  public: // pinOn/Off - 0-127=hw pin, 128+[0..7]=serial pin
    digitalPin(const uint8_t id, const uint8_t pinSwitch, const uint8_t pinOn, const uint8_t pinOff);
    void updateSwitch();
    void updateLedState(const uint8_t c, const uint8_t val);
    void updateLed(const bool blink) ;
    uint8_t getId() const { return(m_id); }
    uint8_t getOnOffBits() const; // return object where serial bits are on/off according to state m_OnLed+m_Offled
  private:
    const uint8_t m_id, m_pinSwitch, m_pinOn, m_pinOff;
    uint8_t m_OnLed { LOW };
    uint8_t m_OffLed { LOW };
    uint8_t m_lastPinState { HIGH } ;
    uint8_t m_lastLedState { 0 } ; // bits: 0=GxON, 1=RxON, 2=GxBLINK, 3=RxBLINK
};

// id=0..12
digitalPin digiPins[] = {
  digitalPin(0,2,0,0),    // OLED mode1 switch 2
  digitalPin(1,3,0,0),    // OLED mode2 switch 3
  digitalPin(2,4,0,0),    // LCD mode1 switch 4
  digitalPin(3,5,0,0),    // LCD mode2 switch 5
  digitalPin(4,6,0+0x80,4+0x80),    // light, switch pin 6, green led 0, red led 4
  digitalPin(5,7,1+0x80,5+0x80),    // gear, switch pin 7, green led 1, red led 5
  digitalPin(6,8,2+0x80,6+0x80),    // RCS, switch pin 8, green led 2, red led 6
  digitalPin(7,9,3+0x80,7+0x80),    // SAS, switch pin 9, green led 3, red led 7
  digitalPin(8,10,0,0),    // stage, switch pin 10
  digitalPin(9,11,0,0),    // stagemode, switch pin 11
  digitalPin(10,0,0,12),    // low fuel, yellow led 12
  digitalPin(11,0,0,13),    // low power, yellow led 13
  digitalPin(12,0,0,A0),    // overheat, red led 14=A0
};

digitalPin::digitalPin(const uint8_t id, const uint8_t pinSwitch, const uint8_t pinOn, const uint8_t pinOff) :
  m_id(id), m_pinSwitch(pinSwitch), m_pinOn(pinOn), m_pinOff(pinOff)
{
  if (m_pinSwitch>0) {
    pinMode(m_pinSwitch,INPUT_PULLUP);
  }
  if (m_pinOn>0 && m_pinOn<128) {
    pinMode(m_pinOn,OUTPUT);
    digitalWrite(m_pinOn,LOW);
  }
  if (m_pinOff>0 && m_pinOn<128) {
    pinMode(m_pinOff,OUTPUT);
    digitalWrite(m_pinOff,LOW);
  }
}

void digitalPin::updateSwitch() {
  if (m_pinSwitch>0) {
    // reverse logic because switches are connected to GND with internal pullup, so pushed state (ON) is 0V
    uint8_t state = !digitalRead(m_pinSwitch);
    if (state!=m_lastPinState) {
      Serial.write('D');
      Serial.print(m_id);
      Serial.write('=');
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

void digitalPin::updateLed(const bool blink) {
  uint8_t nstate;
  nstate = (m_lastLedState & 0x01) ? HIGH : LOW;
  if (nstate==HIGH && (m_lastLedState & 0x02) && blink) {
    nstate = !m_OnLed;
  }
  m_OnLed = nstate;
  if (m_pinOn>0 && m_pinOn<128) {
    digitalWrite(m_pinOn,m_OnLed);
  }

  nstate = (m_lastLedState & 0x10) ? HIGH : LOW;
  if (nstate==HIGH && (m_lastLedState & 0x20) && blink) {
    nstate = !m_OffLed;
  }
  m_OffLed = nstate;
  if (m_pinOff>0 && m_pinOff<128) {
    digitalWrite(m_pinOff,m_OffLed);
  }
}

uint8_t digitalPin::getOnOffBits() const {
  uint8_t nstate = 0;
  if (m_pinOn>=128 && m_OnLed) {
    nstate |= 1 << (m_pinOn & 0x07);
  }
  if (m_pinOff>=128 && m_OffLed) {
    nstate |= 1 << (m_pinOff & 0x07);
  }
  return(nstate);
}

// blinker control
unsigned long lastBlink = 0;
const unsigned long blinkInterval = 500;

void serialShiftWrite(uint8_t data) {
  digitalWrite(latchPin, LOW);
  delayMicroseconds(100);
  // shift the bytes out:
  shiftOut(dataPin, clockPin, MSBFIRST, data);
  delayMicroseconds(100);
  digitalWrite(latchPin, HIGH);
}

// serial port
#define SERIAL_SPEED 115200

void setup() {
  //set pins to output so you can control the shift register
  pinMode(latchPin, OUTPUT);
  pinMode(clockPin, OUTPUT);
  pinMode(dataPin, OUTPUT);
  // initialize serial communications at 9600 bps:
  Serial.begin(SERIAL_SPEED);
  // set timeout to 200ms
  Serial.setTimeout(200);
  // request status update
  Serial.println("I");
  // start blink counter
  lastBlink = millis();
}

void updatePins() {
  const unsigned long currentMillis = millis();
  bool blink = false;
  uint8_t shiftLeds = 0;
  // is it time for tick?
  if (((unsigned long)(currentMillis - lastBlink) >= blinkInterval)) {
    blink = true;
    lastBlink = currentMillis;
  }
  for (auto &p : digiPins) {
    p.updateLed(blink);
    p.updateSwitch();
    shiftLeds |= p.getOnOffBits();
  }
  serialShiftWrite(shiftLeds);
}

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

void checkSerialInput() {
  if (Serial.available()>0) {
    const uint8_t c = Serial.read();
    if (c == 'L') {
	    handleSerialInputLed();
	  }
  }
}

void loop() {
  checkSerialInput();
  updatePins();
  delay(100);
}

