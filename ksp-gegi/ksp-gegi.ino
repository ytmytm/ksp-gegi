
#include <Arduino.h>

// circuit
const int throttlePin = A0;  // P0: Analog input pin that the potentiometer is attached to
const int stagePin = 4;      // D0: Digital input pin that STAGE button is attached to

const int RCSPin = 5;        // D1: RCS switch
const int ledRCSonPin = 6;   // G1: RCS status ON (green)
const int ledRCSoffPin = 7;  // R1: RCS status OFF (red)

const int SCSPin = 8;        // D2: SCS switch
const int ledSCSonPin = 9;   // G2: SCS status ON (green)
const int ledSCSoffPin = 10; // R2: SCS status OFF (red)

// throttle control
int lastThrottleValue = 0;
int throttleValue = 0;
int throttleMin = 1023;
int throttleMax = 0;

// switch control
uint8_t lastStageState = HIGH;
uint8_t lastRCSState = HIGH;
uint8_t lastSCSState = HIGH;

void setup() {
  // initialize serial communications at 9600 bps:
  Serial.begin(38400); 
  // make button pins inputs
  pinMode(stagePin,INPUT_PULLUP);
  pinMode(RCSPin,INPUT_PULLUP);
  pinMode(SCSPin,INPUT_PULLUP);
  // make LED pins outputs
  pinMode(ledRCSonPin,OUTPUT);
  pinMode(ledRCSoffPin,OUTPUT);
  pinMode(ledSCSonPin,OUTPUT);
  pinMode(ledSCSoffPin,OUTPUT);
  // turn off all leds
  digitalWrite(ledRCSonPin,LOW);
  digitalWrite(ledRCSoffPin,LOW);
  digitalWrite(ledSCSonPin,LOW);
  digitalWrite(ledSCSoffPin,LOW);
  // set timeout to 200ms
  Serial.setTimeout(200);
  // request status update
  Serial.println("I");
}

void updateThrottle() {
  // read the analog in value:
  throttleValue = analogRead(throttlePin);
  // calibrate
  if (throttleValue>throttleMax) { throttleMax=throttleValue; }
  if (throttleValue<throttleMin) { throttleMin=throttleValue; }
  // map it to the range of the analog out:
  throttleValue = map(throttleValue, throttleMin, throttleMax, 0, 255);
  // is it different enough from last reading?
  if (abs(throttleValue-lastThrottleValue)>4) {
    // dump status
    Serial.print("P0=");
    Serial.println(throttleValue,HEX);
  }
  lastThrottleValue = throttleValue;
}

uint8_t updateButton(int pin, int id, uint8_t lastState) {
  uint8_t state = digitalRead(pin);
  if (state != lastState) {
    Serial.print('D');
    Serial.print(id);
    Serial.print('=');
    Serial.println(state);
  }
  return(state);
}

void updateStage() {
  lastStageState = updateButton(stagePin,0,lastStageState);
}

void updateRCS() {
  lastRCSState = updateButton(RCSPin,1,lastRCSState);
}

void updateSCS() {
  lastSCSState = updateButton(SCSPin,2,lastSCSState);
}

void checkSerialInput() {
  char c;
  int ledpin=0,val=0,id=0;
  // format: "^LG1=0$" turn off green led 1 (RCS), "^LR2=1$" turn off red led 2 (SCS)
  if (Serial.find("L")) {
    c = Serial.read();
    id = Serial.parseInt();  // skip '='
    val = Serial.parseInt(); // skip newline
    Serial.print(c); Serial.print(id); Serial.print(val);  // echo
    if (c=='G' && id==1) { ledpin = ledRCSonPin; }
    if (c=='R' && id==1) { ledpin = ledRCSoffPin; }
    if (c=='G' && id==2) { ledpin = ledSCSonPin; }
    if (c=='R' && id==2) { ledpin = ledSCSoffPin; }
    if (ledpin>0) {
      if (val==0) {
        digitalWrite(ledpin,LOW);
      } else {
        digitalWrite(ledpin,HIGH);
      }
    }
  }
}

void loop() {
  updateThrottle();
  updateStage();
  updateRCS();
  updateSCS();
  checkSerialInput();
  // wait 2 milliseconds before the next loop
  // for the analog-to-digital converter to settle
  // after the last reading:
  delay(2);                     
}

