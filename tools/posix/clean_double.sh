#!/bin/bash
old_hash="test"
old_file=""
items=`find . -type f -exec md5 '{}' ';' | sort` 
#for item in $items
find . -type f -exec md5 -r '{}' ';' | sort | while read line
do
	hash=${line:0:32}
	#echo "Hash: $hash"
	file_name=${line:33}
	#echo "Filename: $file_name"
	if [ $hash == $old_hash ]; then
		if [ "`dirname "$file_name"`" == "`dirname "$old_file"`" ]; then
			echo "Found duplicate: $file_name"
			if [ "$1" == "-f" ]; then
				rm "$file_name"
			fi
		fi
	fi
	old_hash=$hash
	old_file=$file_name
done
