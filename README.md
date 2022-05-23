![banner](https://github.com/adamhlt/TL-WR841N/blob/main/Ressources/banner.png)

# TL-WR841N

[![Linux](https://img.shields.io/badge/platform-Linux-0078d7.svg?style=for-the-badge&logo=appveyor)](https://fr.wikipedia.org/wiki/Linux) [![x86](https://img.shields.io/badge/arch-MIPS-red.svg?style=for-the-badge&logo=appveyor)](https://fr.wikipedia.org/wiki/Architecture_MIPS)

## 📖 Project Overview :

I created this project to discover hardware hacking, I started with an old router (TP LINK TL-WR841N).

##### Project goals :

- Identify the series port
- Connect to the series port
- Make a full dump of the firmware
- Reverse the firmware
- Backdooring the firmware
- (Optionaly) Understand firmware emulation

I show you my journey of starting hardware hacking, and what I can achieved or not.

I will try to be the more descriptive I can, in every steps.

## 🚀 Getting Started

This is the list of every softwares and equipement I use.

##### Equipements :

- Router (TP LINK TL-WR841N)
- Multimeter (with continuity mode)
- Logic analyser (DSLogic U2 Basic)
- TTL to USB converter (DSD TECH SH-U09C5)
- Flash programmer (CH341A)
- SOIC8 clip



##### Software :

- Logic analyser (dsview)
- Series port communication (putty / screen)
- binary analyser (binwalk)
- (Optionaly) MIPS emulator (qemu)



## :computer: Start Hacking

##### External router photo :

![External Photo](https://github.com/adamhlt/TL-WR841N/blob/main/Ressources/img1.png?raw=true)

##### Internal router photo (I unsoldered the antennas) :

![Internal Photo](https://github.com/adamhlt/TL-WR841N/blob/main/Ressources/img2.png?raw=true)

### 1 - Identify components 

On the internal photo we can see a lot of things, first on the left we can notice that we have severals connectors, the one which contains 4 pins can be UART port or another series port.

Then, on the right side of the board there are two 8 pin chip, one of them can be flash memory or eeprom and can contains the firmware.

![Internal Demo](https://github.com/adamhlt/TL-WR841N/blob/main/Ressources/img9.png?raw=true)



### 2 - Test potentiel series port

To test the 4 pin series port, I start by trying to find the ground with my multimeter in continuity mode.

As I expect I can easily find the ground, then with my multimeter I looked for other pins, the output is 3,3 V. The two last pins, seems to be RX and TX, one is 0 V and the other oscillate, which can mean it send datas. 

![Pins Photo](https://github.com/adamhlt/TL-WR841N/blob/main/Ressources/img3.png?raw=true)



### 3 - Use logic analyser

So, after soldering pins to test outputs easier, I can use my logic analyser to see datas and try to identify the protocol.



