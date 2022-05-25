![Banner](https://user-images.githubusercontent.com/48086737/170033919-fdad0cfb-926b-4d0f-9433-55660431b53e.png)

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

![External Photo](https://user-images.githubusercontent.com/48086737/169881510-b52a471b-d75e-4fc9-a1a1-d8d527619881.png)

##### Internal router photo (I unsoldered the antennas) :

![Internal Photo](https://user-images.githubusercontent.com/48086737/169884723-451c9852-20cc-4345-a31e-fafebdfe34ac.png)

### 1 - Identify components 

On the internal photo we can see a lot of things, first on the left we can notice that we have severals connectors, the one which contains 4 pins can be UART port or another series port.

Then, on the right side of the board there are two 8 pin chip, one of them can be flash memory or eeprom and can contains the firmware.

![Internal Demo](https://user-images.githubusercontent.com/48086737/169885420-79085ad9-3837-423b-bcee-231088dcc52d.png)

### 2 - Test potentiel series port

To test the 4 pin series port, I start by trying to find the ground with my multimeter in continuity mode.

As I expect I can easily find the ground, then with my multimeter I looked for other pins, the output is 3,3 V. The two last pins, seems to be RX and TX, one is 0 V and the other oscillate, which can mean it send datas. 

![Pins Demo](https://user-images.githubusercontent.com/48086737/169885011-302efd2d-11a3-4144-8e08-0c2a5b260c77.png)


### 3 - Use logic analyser

So, after soldering pins to test outputs easier, I can use my logic analyser to see datas and try to identify the protocol.

![Logic Analyser 1](https://user-images.githubusercontent.com/48086737/169893802-85cd8f60-4fab-4e5e-a780-f7cb92d65014.png)

![Logic Analyser 2](https://user-images.githubusercontent.com/48086737/169894288-e99b0975-9b63-413f-9b43-00f5cba3f7ff.png)


After everthing is connected I can start DSView, config the logic analyzer and start the router to try to capture the outputs.

![DSView](https://user-images.githubusercontent.com/48086737/169894454-6a75ece9-2719-4fc9-9c2f-186f3df3b987.png)

The captured datas are correctly recognized as UART communications and we can see the a part of the logs in ASCII.

This is a part of decoded datas I collected (entire datas [here](https://github.com/adamhlt/TL-WR841N/files/8757659/logic.analyser.txt) :

```
Id,Time[ns],0:UART: RX/TX
0,54414000.00000000000000000000,[FF]
1,312890000.00000000000000000000,[0D]
2,312974000.00000000000000000000,[8A]
3,313057000.00000000000000000000,[0D]
4,313140000.00000000000000000000,[0A]
5,313223000.00000000000000000000,U
6,313306000.00000000000000000000,-
7,313389000.00000000000000000000,B
8,313473000.00000000000000000000,o
9,313556000.00000000000000000000,o
10,313639000.00000000000000000000,t
11,313722000.00000000000000000000, 
12,313805000.00000000000000000000,1
13,313889000.00000000000000000000,.
14,313972000.00000000000000000000,1
15,314055000.00000000000000000000,.
16,314138000.00000000000000000000,4
17,314221000.00000000000000000000, 
18,314305000.00000000000000000000,(
19,314388000.00000000000000000000,M
20,314471000.00000000000000000000,a
21,314554000.00000000000000000000,r
22,314637000.00000000000000000000, 
23,314721000.00000000000000000000,1
24,314804000.00000000000000000000,0
25,314887000.00000000000000000000, 
26,314970000.00000000000000000000,2
27,315053000.00000000000000000000,0
28,315137000.00000000000000000000,1
29,315220000.00000000000000000000,5
30,315303000.00000000000000000000, 
31,315386000.00000000000000000000,-
32,315469000.00000000000000000000, 
33,315553000.00000000000000000000,1
34,315636000.00000000000000000000,5
35,315719000.00000000000000000000,:
36,315802000.00000000000000000000,0
37,315885000.00000000000000000000,0
38,315969000.00000000000000000000,[BA]
39,316052000.00000000000000000000,3
40,316135000.00000000000000000000,4
41,316218000.00000000000000000000,)
42,316301000.00000000000000000000,[0D]
43,316385000.00000000000000000000,[8A]
44,316468000.00000000000000000000,[0D]
45,316551000.00000000000000000000,[0A]
46,316634000.00000000000000000000,a
47,316717000.00000000000000000000,p
48,316801000.00000000000000000000,[B1]
49,316884000.00000000000000000000,4
50,316967000.00000000000000000000,3
```

We can indetify that's the router use [U-Boot](https://fr.wikipedia.org/wiki/Das_U-Boot) boot loader.

Next step is to connect pins to TTL to USB converter and try to get a shell.

### 3 - Try to get a shell

Now, I'm trying to get a shell on the device via UART, I'm using my TTL to USB adapter.

When you connect adapter or any device which communicate using UART you should be careful about the way you plug the cables.

##### You have to plug the cables like this :

##### ![uart-tx-rx-cross](https://user-images.githubusercontent.com/48086737/170241688-4efa98fe-b2dd-4cb2-8971-9d09f82994c5.png)

##### My setup :
