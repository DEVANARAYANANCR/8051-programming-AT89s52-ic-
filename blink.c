#include <reg52.h>          // AT89S52 register definitions (Keil C51)

sbit LED = P1^0;             // LED on P1.0 (through a 330 ohm resistor)

/* ~1 ms per count with 11.0592 MHz crystal */
void delay(unsigned int count) {
    unsigned int i, j;
    for (i = 0; i < count; i++)
        for (j = 0; j < 111; j++);
}

void main(void) {
    while (1) {
        LED = 0;             // LED ON  (if wired as sink: Vcc -> LED -> resistor -> pin)
        delay(500);          // 500 ms
        LED = 1;             // LED OFF
        delay(500);          // 500 ms
    }
}
