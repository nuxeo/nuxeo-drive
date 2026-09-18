/**
 * Copyright (c) 2000-2013 Liferay, Inc. All rights reserved.
 * © 2012-2026 Hyland.
 * All Hyland product names are registered or unregistered trademarks of Hyland or its affiliates.
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

#ifndef REGISTRYUTIL_H
#define REGISTRYUTIL_H

#pragma once

#pragma warning (disable : 4251)

#include <string>
#include <windows.h>

class __declspec(dllexport) RegistryUtil
{
	public:
		RegistryUtil();
		~RegistryUtil();

		static bool ReadRegistry(const wchar_t*,  const wchar_t*, int*);

		static bool ReadRegistry(const wchar_t*,  const wchar_t*, std::wstring*);
};

#endif
