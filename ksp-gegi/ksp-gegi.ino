
#include <Arduino.h>

// P0:
// potencjometr od nawilżacza
// nieprzylutowane -> GND, środek (czerwony pasek) -> A0, przylutowane -> 5V
// kalibracja: po włączeniu przekręcić w obie skrajne pozycje
// D0:
// zielona strona, pomiędzy GND a D4

// circuit
const int throttlePin = A0;  // P0: Analog input pin that the potentiometer is attached to

const uint8_t nPins = 2;
const uint8_t switchPins[] = {4, 5, 8};	// Dx: stage, RCS, SAS switch
const uint8_t onPins[] = {0, 13, 9};	// Gx: stage, RCS, SAS ON (green)
const uint8_t offPins[] = {0, 7, 10};	// Rx: stage, RCS, SAS OFF (red)
uint8_t lastPinState[] = {HIGH, HIGH, HIGH};

// throttle control
int lastThrottleValue = 0;
int throttleValue = 0;
int throttleMin = 1023;
int throttleMax = 0;
#define THROTTLE_THRESHOLD 4

void setup() {
  // initialize serial communications at 9600 bps:
  Serial.begin(38400); 
  // make button pins inputs
  for (uint8_t i=0; i<nPins; i++) {
	// switch pin input
	if (switchPins[i]>0) { pinMode(switchPins[i],INPUT_PULLUP); }
        // make LED pins outputs+turn off
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
  uint8_t ledPin=0,val=0,id=0;
  // format: "^LG1=0$" turn off green led 1 (RCS), "^LR2=1$" turn off red led 2 (SCS)
  if (Serial.available()>0) {
  if (Serial.find("L")) {
    c = Serial.read();
    id = Serial.parseInt();  // skip '='
    val = Serial.parseInt(); // skip newline
    Serial.print(c); Serial.print(id); Serial.println(val);  // echo for ack
	if (id<nPins) {
		if (c=='G') { ledPin = onPins[id]; }
		if (c=='R') { ledPin = offPins[id]; }
		if (ledPin>0) {
			if (val==0) {
				digitalWrite(ledPin,LOW);
			} else {
				digitalWrite(ledPin,HIGH);
			}
		}
	}
  }
  }
}

void loop() {
  updateThrottle();
  updatePins();
  checkSerialInput();
  delay(200);
}
