/**
 * Copyright (c) 2000-2013 Liferay, Inc. All rights reserved.
 * Copyright (c) 2024 Hyland Software, Inc. and its affiliates. All rights reserved. All Hyland product names are registered or unregistered trademarks of Hyland Software, Inc. or its affiliates.
 *
 * This library is free software; you can redistribute it and/or modify it under
 * the terms of the GNU Lesser General Public License as published by the Free
 * Software Foundation; either version 2.1 of the License, or (at your option)
 * any later version.
 *
 * This library is distributed in the hope that it will be useful, but WITHOUT
 * ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
 * FOR A PARTICULAR PURPOSE. See the GNU Lesser General Public License for more
 * details.
 */

#include "DriveMessage.h"

using namespace std;

DriveMessage::DriveMessage(void)
{
	_command = new wstring();
	_value = new wstring();
}

DriveMessage::~DriveMessage(void)
{
}

std::wstring* DriveMessage::GetCommand()
{
	return _command;
}

std::wstring* DriveMessage::GetValue()
{
	return _value;
}

void DriveMessage::SetCommand(std::wstring* command)
{
	_command = command;
}

void DriveMessage::SetValue(std::wstring* value)
{
	_value = value;
}
