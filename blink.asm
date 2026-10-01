;==============================================================
;  LED Blink - AT89S52 (8051), 11.0592 MHz crystal
;  LED on P1.0 (through a 330 ohm resistor), 500 ms ON / 500 ms OFF
;==============================================================

LED         BIT 90h         ; P1.0

            ORG 0000h
            LJMP START

            ORG 0030h
START:
            MOV  SP, #60h
BLINK:
            CLR  LED                ; LED ON  (sink wiring: Vcc -> LED -> resistor -> pin)
            MOV  R4, #HIGH 500      ; 500 ms
            MOV  R5, #LOW 500
            ACALL DELAY_MS

            SETB LED                ; LED OFF
            MOV  R4, #HIGH 500      ; 500 ms
            MOV  R5, #LOW 500
            ACALL DELAY_MS

            SJMP BLINK

;--------------------------------------------------------------
; DELAY_MS : delay = R4:R5 milliseconds (R4 = high, R5 = low)
;--------------------------------------------------------------
DELAY_MS:
DMS_LOOP:
            ACALL DELAY_1MS
            MOV  A, R5
            JNZ  DMS_SKIP
            DEC  R4
DMS_SKIP:
            DEC  R5
            MOV  A, R4
            ORL  A, R5
            JNZ  DMS_LOOP
            RET

; DELAY_1MS : ~923 machine cycles = ~1 ms at 11.0592 MHz
DELAY_1MS:
            MOV  R7, #2
D1MS_OUT:
            MOV  R6, #228
            DJNZ R6, $
            DJNZ R7, D1MS_OUT
            RET

            END
