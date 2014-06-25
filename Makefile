thanks:
	if [ -f THANKS ]; then rm THANKS; fi
	echo "Thanks to the following folks who contributed to bipython!" > THANKS
	echo "" >> THANKS
	echo "commits   Name" >> THANKS
	echo "------- -------------" >> THANKS
	git shortlog -sn >> THANKS

.PHONE: thanks
