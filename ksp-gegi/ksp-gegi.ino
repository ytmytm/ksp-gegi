
#include <Arduino.h>

// dł kabelków 15-20cm
// diody LED: niebieskie (bez rezystora, krótka nóżka) do GND, białe (z rezystorem, długa nóżka) do pinu
// potencjometr: niebieski z czarną kreską do GND, biały do +5V, niebieski do pinu A0
// przełączniki2: niebieski do GND, biały do pinu, wszystkie zamontowane tak, aby niebieski był w środku, biały na dole, a niepodłączone u góry (wtedy gałka w górę==załączenie)
// przełączniki3: środkowy (ciemny) do GND, boczne do pinów

// przepisać tablice+npins jako klasę?
// to: oraz array.size() zamiast nPins http://hackaday.com/2015/11/13/code-craft-embedding-c-timing-virtual-functions/
//   ok jeśli będzie niedużo gorsze od 5104 bajtów

const int throttlePin = A0;  // P0

const uint8_t nPins = 7; // długość tabel poniżej
const uint8_t switchPins[] = {4,  5, 8, 12, 0, 0,  0};	// Dx: stage, RCS, SAS, gear switch, overheat, lowpower, lowfuel
const uint8_t onPins[] =     {0, 13, 9,  0, 0, 0,  0};	// Gx: stage, RCS, SAS, overheat, lowpower, lowfuel ON (green)
const uint8_t offPins[] =    {0,  0, 0,  0, 6, 7, 10};	// Rx: stage, RCS, SAS, overheat, lowpower, lowfuel OFF (red)
uint8_t lastPinState[] = {HIGH, HIGH, HIGH, HIGH, HIGH, HIGH, HIGH};
uint8_t lastLedState[] =  {0, 0, 0, 0, 0, 0, 0};	// bits: 0=GxON, 1=RxON, 2=GxBLINK, 3=RxBLINK

// blinker control
unsigned long lastBlink = 0;
const unsigned long blinkInterval = 500;

// throttle control
int lastThrottleValue = 0;
int throttleValue = 0;
int throttleMin = 1023;
int throttleMax = 0;
#define THROTTLE_THRESHOLD 2
#define SERIAL_SPEED 9600

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
}

void updateThrottle() {
  // read the analog in value:
  throttleValue = analogRead(throttlePin);
  // auto calibrate
  if (throttleValue>throttleMax) { throttleMax=throttleValue; }
  if (throttleValue<throttleMin) { throttleMin=throttleValue; }
  // map it to the range of the analog out:
  throttleValue = map(throttleValue, throttleMin, throttleMax, 0, 255);
  // is it different enough from last reading?
  if (abs(throttleValue-lastThrottleValue)>THROTTLE_THRESHOLD) {
    if (throttleValue<THROTTLE_THRESHOLD) {
      throttleValue = 0;
    }
    if (throttleValue>255-THROTTLE_THRESHOLD) {
      throttleValue = 255;
    }
    // dump status
    Serial.print("P0=");
    Serial.println(throttleValue,HEX);
    lastThrottleValue = throttleValue;
  }
}

uint8_t updateButton(int pin, int id, uint8_t lastState) {
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

void checkSerialInput() {
  uint8_t c;
  uint8_t val=0,id=0,nval=0;
  // format: "^LG1=0$" turn off green led 1 (RCS), "^LR2=1$" turn off red led 2 (SCS)
  if (Serial.available()>0) {
  if (Serial.find("L")) {
    c = Serial.read();
    id = Serial.parseInt();  // skip '='
    val = Serial.parseInt(); // skip newline
//    Serial.print(c); Serial.print(id); Serial.println(val);  // echo for ack
	if (id>0 && id<=nPins) {
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
  updateThrottle();
  updatePins();
  checkSerialInput();
  updateLeds();
  delay(200);
}

