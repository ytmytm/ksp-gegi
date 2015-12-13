
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

// przepisać tablice+npins jako klasę?
// to: oraz array.size() zamiast nPins http://hackaday.com/2015/11/13/code-craft-embedding-c-timing-virtual-functions/
//   ok jeśli będzie niedużo gorsze od 5104 bajtów

// digital control (switch, red, green)
const uint8_t nPins = 7; // długość tabel poniżej
const uint8_t switchPins[] = {4,  5, 8, 12, 0, 0,  0};	// Dx: stage, RCS, SAS, gear switch, overheat, lowpower, lowfuel
const uint8_t onPins[] =     {0, 13, 9,  0, 0, 0,  0};	// Gx: stage, RCS, SAS, overheat, lowpower, lowfuel ON (green)
const uint8_t offPins[] =    {0,  0, 0,  0, 6, 7,  3};	// Rx: stage, RCS, SAS, overheat, lowpower, lowfuel OFF (red)
uint8_t lastPinState[] = {HIGH, HIGH, HIGH, HIGH, HIGH, HIGH, HIGH};
uint8_t lastLedState[] =  {0, 0, 0, 0, 0, 0, 0};	// bits: 0=GxON, 1=RxON, 2=GxBLINK, 3=RxBLINK

// blinker control
unsigned long lastBlink = 0;
const unsigned long blinkInterval = 500;

// analog control input
const uint8_t nAPins = 2;
const uint8_t aPins[] = {A0, A1};	// pot: throttle, timewarp
int lastAValue[] = {0, 0};
int aValue[] = {0, 0};
const int aThreshold[] = {2, 2};

// analog control output
const uint8_t nAOutPins = 1;
const uint8_t aOutPins[] = {10};	// vmeter: g-force

// Set the pins on the I2C chip used for LCD connections:
//                    addr, en,rw,rs,d4,d5,d6,d7,bl,blpol
LiquidCrystal_I2C lcd(0x3f, 2, 1, 0, 4, 5, 6, 7, 3, POSITIVE);

// serial port
#define SERIAL_SPEED 115200

void setup() {
  // initialize serial communications at 9600 bps:
  Serial.begin(SERIAL_SPEED);
  // make button pins inputs
  for (uint8_t i=0; i<nPins; i++) {
	// switch pin input
	if (switchPins[i]>0) { pinMode(switchPins[i],INPUT_PULLUP); }
    // make LED pins outputs+turn off
	lastLedState[i] = 0;
	if (onPins[i]>0) {
          pinMode(onPins[i],OUTPUT);
          digitalWrite(onPins[i],LOW);
        }
        if (offPins[i]>0) {
          pinMode(offPins[i],OUTPUT);
          digitalWrite(offPins[i],LOW);
        }
  }
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

void updateAnalogPin(uint8_t id) {
	// read in analog value
	aValue[id] = analogRead(aPins[id]);
	// map to the range of the analog out
	aValue[id] = map(aValue[id], 0, 1023, 0, 255);
	// is it different enough from the last reading?
	if (abs(aValue[id]-lastAValue[id])>aThreshold[id]) {
		if (aValue[id]<aThreshold[id]) {
			aValue[id] = 0;
		}
		if (aValue[id]>255-aThreshold[id]) {
			aValue[id] = 255;
		}
    // dump status
	Serial.print("P");
	Serial.print(id);
	Serial.print("=");
	Serial.println(aValue[id],HEX);
	lastAValue[id] = aValue[id];
  }
}

void updateAnalogs() {
	for (uint8_t i=0; i<nAPins; i++) {
		updateAnalogPin(i);
	}
}

uint8_t updateButton(int pin, int id, uint8_t lastState) {
  if (pin==0) {
    return(lastState);
  }
  // reverse logic because switches are connected to GND with internal pullup, so pushed state (ON) is 0V
  uint8_t state = !digitalRead(pin);
  if (state != lastState) {
    Serial.print('D');
    Serial.print(id);
    Serial.print('=');
    Serial.println(state);
  }
  return(state);
}

void updatePins() {
	for (uint8_t i=0; i<nPins; i++) {
		lastPinState[i] = updateButton(switchPins[i],i,lastPinState[i]);
	}
}

// commands like: ^L{GR}{id}={val}$
// format: "^LG1=0$" turn off green led 1 (RCS), "^LR2=1$" turn off red led 2 (SCS)
void handleSerialInputLed() {
    uint8_t c;
    uint8_t val=0,id=0,nval=0;
    c = Serial.read();
    id = Serial.parseInt();  // skip '='
    val = Serial.parseInt(); // skip newline
//    Serial.print(c); Serial.print(id); Serial.println(val);  // echo for ack
	if (id>=0 && id<=nPins) {
                nval = lastLedState[id];
                if (c=='G') {
                  nval = nval & 0b11111010;
                  if (val==1) nval=nval | 0x01;
                  if (val==2) nval=nval | 0x01 | 0x04;
                }
                if (c=='R') {
                  nval = nval & 0b11110101;
                  if (val==1) nval=nval | 0x02;
                  if (val==2) nval=nval | 0x02 | 0x08;
                }
		lastLedState[id] = nval;
	}
}

// commands like ^A{id}={val}$
void handleSerialInputAnalogOut() {
    uint8_t val=0,id=0;
    id = Serial.parseInt();  // skip '='
    val = Serial.parseInt(); // skip newline
//    Serial.print(id); Serial.println(val);  // echo for ack
	if (id>=0 && id<=nAOutPins) {
		analogWrite(aOutPins[id], val);
	}
}

// commands like ^P{line:0,1}={text0..15}$ (consume all characters until end of the line)
void handleSerialInputLCD() {
    uint8_t id=0, i=0, c;
    id = Serial.parseInt();
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
//        Serial.println("endLCD");
	}
}

void checkSerialInput() {
  uint8_t c;
  if (Serial.available()>0) {
    c = Serial.read();
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

// set all LEDs according to state
void updateLeds() {
  unsigned long currentMillis = millis();
  bool blink = false;
  // is it time for tick?
  if (((unsigned long)(currentMillis - lastBlink) >= blinkInterval)) {
	  blink = true;
	  lastBlink = currentMillis;
  }
//  Serial.print("blink="); Serial.println(blink);
  // update all leds
  for (uint8_t i=0; i<nPins; i++) {
	uint8_t nstate;
	uint8_t gPin = onPins[i];
	if (gPin!=0) {
		nstate = (lastLedState[i] & 0x01) ? HIGH : LOW;
		if (nstate==HIGH && (lastLedState[i] & 0x04) && blink) {
			nstate = !digitalRead(gPin);
		}
//Serial.print("L"); Serial.print(gPin); Serial.print(nstate);
		digitalWrite(gPin,nstate);
	}
	uint8_t rPin = offPins[i];
	if (rPin!=0) {
		nstate = (lastLedState[i] & 0x02) ? HIGH : LOW;
		if (nstate==HIGH && (lastLedState[i] & 0x08) && blink) {
			nstate = !digitalRead(rPin);
		}
//Serial.print("R"); Serial.print(rPin); Serial.print(nstate);
		digitalWrite(rPin,nstate);
	}
  }
}

void loop() {
  updateAnalogs();
  updatePins();
  checkSerialInput();
  updateLeds();
//  delay(200);
}
