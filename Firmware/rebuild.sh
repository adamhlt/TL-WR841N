#!/bin/bash

if ! test -d "firmware_extract"; then
        printf "No files to build the image !\n\n"
	exit 0
fi

if ! test -f "cfw.bin"; then
        touch cfw.bin
	printf "Custom firmware file created !\n\n"
else
	rm cfw.bin
	printf "Old cfw file removed!\n\n"
fi

if test -f "firmware_extract/firmware_part1.bin"; then
	dd if=firmware_extract/firmware_part1.bin of=cfw.bin bs=1 skip=0 count=12928
	printf "Part 1 builded\n\n"
else
	printf "Image part 1 is missing !\n\n"
	exit 0
fi

if test -f "firmware_extract/firmware_part2.bin"; then
        dd if=firmware_extract/firmware_part2.bin of=cfw.bin bs=1 skip=0 count=48 seek=12928
        printf "Part 2 builded\n\n"
else
        printf "Image part 2 is missing !\n\n"
        exit 0
fi

if test -f "firmware_extract/firmware_part3.bin"; then
        dd if=firmware_extract/firmware_part3.bin of=cfw.bin bs=1 skip=0 count=1312 seek=12976
        printf "Part 3 builded\n\n"
else
        printf "Image part 3 is missing !\n\n"
        exit 0
fi

if test -f "firmware_extract/firmware_part4.bin"; then
        dd if=firmware_extract/firmware_part4.bin of=cfw.bin bs=1 skip=0 count=64 seek=14288
        printf "Part 4 builded\n\n"
else
        printf "Image part 4 is missing !\n\n"
        exit 0
fi

if test -f "firmware_extract/firmware_part5.bin"; then
        dd if=firmware_extract/firmware_part5.bin of=cfw.bin bs=1 skip=0 count=116720 seek=14352
        printf "Part 5 builded\n\n"
else
        printf "Image part 5 is missing !\n\n"
        exit 0
fi

if test -f "firmware_extract/firmware_part6.bin"; then
        dd if=firmware_extract/firmware_part6.bin of=cfw.bin bs=1 skip=0 count=512 seek=131072
        printf "Part 6 builded\n\n"
else
        printf "Image part 6 is missing !\n\n"
        exit 0
fi

if test -f "firmware_extract/firmware_part7.bin"; then
        dd if=firmware_extract/firmware_part7.bin of=cfw.bin bs=1 skip=0 count=1048064 seek=131584
        printf "Part 7 builded\n\n"
else
        printf "Image part 7 is missing !\n\n"
        exit 0
fi

if test -f "firmware_extract/firmware_part8.bin"; then
        dd if=firmware_extract/firmware_part8.bin of=cfw.bin bs=1 skip=0 count=3014656 seek=1179648
        printf "Part 8 builded\n\n"
else
        printf "Image part 8 is missing !\n\n"
        exit 0
fi

printf "Cfw builded successfully\n\n"
