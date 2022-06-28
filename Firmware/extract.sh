#!/bin/bash

if ! test -f "firmware.bin"; then
	printf "Firmware file not found !\n\n"
	exit -1
fi

cp firmware.bin firmware.bck
printf "Backup file created\n\n"

if ! test -d "firmware_extract"; then
	mkdir firmware_extract
	printf "Extract directory created !\n\n"
else
	sudo rm -r firmware_extract
	printf "Extract directory removed !\n\n"
	mkdir firmware_extract
        printf "Extract directory created !\n\n"
fi

touch firmware_extract/firmware_part1.bin
dd if=firmware.bin of=firmware_extract/firmware_part1.bin bs=1 skip=0 count=12928
printf "Header extract > firmware_part1.bin\n\n"

touch firmware_extract/firmware_part2.bin
dd if=firmware.bin of=firmware_extract/firmware_part2.bin bs=1 skip=12928 count=48
printf "UBoot string extract > firmware_part2.bin\n\n"

touch firmware_extract/firmware_part3.bin
dd if=firmware.bin of=firmware_extract/firmware_part3.bin bs=1 skip=12976 count=1312
printf "CRC32 polynomial table extract > firmware_part3.bin\n\n"

touch firmware_extract/firmware_part4.bin
dd if=firmware.bin of=firmware_extract/firmware_part4.bin bs=1 skip=14288 count=64
printf "uImage header extract > firmware_part4.bin\n\n"

touch firmware_extract/firmware_part5.bin
dd if=firmware.bin of=firmware_extract/firmware_part5.bin bs=1 skip=14352 count=116720
printf "LZMA compressed data extract > firmware_part5.bin\n\n"

touch firmware_extract/firmware_part6.bin
dd if=firmware.bin of=firmware_extract/firmware_part6.bin bs=1 skip=131072 count=512
printf "TP-Link firmware header extract > firmware_part6.bin\n\n"

touch firmware_extract/firmware_part7.bin
dd if=firmware.bin of=firmware_extract/firmware_part7.bin bs=1 skip=131584 count=1048064
printf "LZMA compressed data > firmware_part7.bin\n\n"

touch firmware_extract/firmware_part8.bin
dd if=firmware.bin of=firmware_extract/firmware_part8.bin bs=1 skip=1179648 count=2883584
printf "Squashfs filesystem extract > firmware_part8.bin\n\n"

touch firmware_extract/firmware_part9.bin
dd if=firmware.bin of=firmware_extract/firmware_part9.bin bs=1 skip=4063232 count=131072
printf "config > firmware_part9.bin\n\n"

sudo unsquashfs firmware_extract/firmware_part8.bin

printf "Firmware successfully extracted !\n\n"
