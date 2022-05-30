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

![External Photo](https://user-images.githubusercontent.com/48086737/170682620-f0b01329-ec6b-41ec-9d74-0b974ef3a716.jpg)

##### Internal router photo (I unsoldered the antennas) :

![Internal Photo](https://user-images.githubusercontent.com/48086737/170682670-7add7410-b7db-45e7-9b18-164d21e6b764.jpg)

### 1 - Identify components 

The first thing I have to do is to identify what is on the board, I am looking for series ports, flash memory / eeprom... On the internal photo we can see a lot of things, first, on the left we can notice that we have severals connectors, the one which contains 4 pins can be UART port or another series port. Then, on the right side of the board there are two 8 pin chip, one of them can be flash memory or eeprom and can contains the firmware.

The next steps are :

1. Test the differents series port with a multimeter
2. Test the differents series port with logic analyser if the multimeter result seems interresting
3. Test the differents chips with a programmer to try to detect them
4. Try to dump chip's memory if the programmer detect the chip

![Internal Demo](https://user-images.githubusercontent.com/48086737/170682756-4c242515-40b0-4e49-bb15-aa4a47a83c88.jpg)

### 2 - Test potentiel series port

To test the 4 pin series port, I start by trying to find the GND with my multimeter in continuity mode (I find it with the GND pin of a chip).

As I expect I can easily find the GND pin, then with my multimeter I looked for the other pins, the first one on the left is the + pin, the voltage is 3,3 V, then the second pin the GND pin. The two last pins, seems to be RX and TX, the third one is 0 V which can be the RX pin waiting for datas, and last one's voltage oscillates (tends to 2,63v), it seems to be the TX pin which transmits the datas.

Now I will use my logic analyser and try to see if these pins send datas.

![Pins Demo](https://user-images.githubusercontent.com/48086737/170682821-88fe605e-e72f-498a-9cd6-2c420fe98d6c.jpg)

### 3 - Using the logic analyser

After I praticaly identify pins, the next step is to see if these pins transmit datas, that is why I connect my logic analyser. The logic analyser just need to be connected to the ground and then to all pins we want to identify, the logic analyser will capture everything that is passings trough the pins and then can identify the protocol and the datas that are transmitted. As you can see I connected the 3 pins, the GND and the "potential" RX and TX pins.

![Logic Analyser 1](https://user-images.githubusercontent.com/48086737/170682898-b13fd3da-eb2a-43ac-a2f3-a2b33d503631.jpg)

![Logic Analyser 2](https://user-images.githubusercontent.com/48086737/170682963-70eb8386-2a83-42fe-b47a-df061057be15.jpg)

After everthing is connected I can start DSView, I record 1 minute of communication just after the startup up of the router. When I use the decode feature the software detect the communication as UART and it start decoding the datas, as you can see on the DSView UI it start decoding : "Linux Version"... 

![DSView](https://user-images.githubusercontent.com/48086737/170683021-6e23dbe9-17a4-4712-814b-23eb6b123923.jpg)

I post bellow a part of decoded datas I collected (entire datas [here](https://github.com/adamhlt/TL-WR841N/files/8757659/logic.analyser.txt) :

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

We can indetify that's the router use [U-Boot](https://fr.wikipedia.org/wiki/Das_U-Boot) boot loader, the logic analyser has his own limitations, I can't get decoded datas in real time and can't interract with the RX pin. So, the final step is to connect the pins to the TTL to USB adapter and try to interract with the device and get a shell.

### 3 - Try to get a shell

The TTL to USB adapter permits to interact with the device in UART using tools like screen or putty. The cables have to be correctly connected, as you can see on the scheme bellow, we also need to know the baudrate to correctly communicate with the device, else the datas will not be decoded correctly and will be junk. I configured my adapter on 3,3v for the RX voltage.

#### You have to plug the cables like this :

##### ![uart-tx-rx-cross](https://user-images.githubusercontent.com/48086737/170241688-4efa98fe-b2dd-4cb2-8971-9d09f82994c5.png)

#### My setup :

![Setup 1](https://user-images.githubusercontent.com/48086737/170683129-c3ca68d9-8d80-46e7-a83a-72ad609ec07b.jpg)

![Setup 2](https://user-images.githubusercontent.com/48086737/170683167-4caebf8f-d8ea-48da-87f5-75ab388f85c9.jpg)

https://user-images.githubusercontent.com/48086737/170248292-8ba71541-bd88-4038-8fe3-116d35919d7b.mp4

After some tests, I conclude that I can't interract with the device and can't get a shell. 

I have some hypothesis about why I can't interract with the device.

Hypothesis :

- The firmware don't listen to RX and use UART just for logging
- The RX signal is not transmit on the board
- The TX signal is not working on the adapter

I will try to solve every hypothesis and find what is the problem, I will start by the easiest to the hardest to solve. I can only test the 2 last hypothesis because I can't know if the firmware has limitations without reversing it.

#### 1 - The TX signal is not working on the adapter

The hypotesis can be easily discarded, on the TTL adapter there is a led that indicate when a signal is send, and it is perfectly working. Moreover when I connect the TX pin to the RX pin of the adapter everything works great.

So, the problem don't come from the adapter.

#### 2 - The RX signal is not transmit on the board

As you can imagine the problem come from the board, after some investigations and be sure that the problem don't come from the adapter, I found where the problem come from. As you can see bellow, there is a missing resistor, this break the continuity and the signal can't go trough. Then, I reestablished the continuity and try to communicate with the device.

![Missing Resistor](https://user-images.githubusercontent.com/48086737/171010421-3175f8e7-ced1-453c-ab1b-43574034db71.jpg)

![Fix Resistor](https://user-images.githubusercontent.com/48086737/171010486-3a6ba0de-a854-4854-8971-4c3abe3c309c.jpeg)

![Fail Screenshot](https://user-images.githubusercontent.com/48086737/171012401-17c9c319-18bc-4d41-ad08-4732c76b02d2.jpg)

As you can see we progress, now the device receive inputs, datas are absolutely junk but we can now access to the login prompt.

At this point the RX voltage is always 3,3v, the device try to decode datas that I never send so we can imagine that the device interpret the voltage as low and think this is a start of communication (according to how UART works). This is a hypothesis but we can imagine that the voltage of RX is too low, the only higher voltage I have is 5v.
