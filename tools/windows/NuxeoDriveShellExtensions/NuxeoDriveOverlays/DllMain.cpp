/**
 * Copyright (c) 2000-2013 Liferay, Inc. All rights reserved.
 * Copyright (c) 2019 Nuxeo. All rights reserved.
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

#include "DriveOverlayRegistrationHandler.h"
#include "DriveOverlayFactory.h"
#include "stdafx.h"

HINSTANCE instanceHandle = NULL;

long dllReferenceCount = 0;


BOOL APIENTRY DllMain(HMODULE hModule, DWORD dwReason, LPVOID lpReserved)
{
	switch (dwReason)
	{
		case DLL_PROCESS_ATTACH:
			instanceHandle = hModule;
			DisableThreadLibraryCalls(hModule);
			break;
		case DLL_THREAD_ATTACH:
		case DLL_THREAD_DETACH:
		case DLL_PROCESS_DETACH:
			break;
	}

	return TRUE;
}

STDAPI DllGetClassObject(REFCLSID rclsid, REFIID riid, void** ppv)
{
	HRESULT hResult = CLASS_E_CLASSNOTAVAILABLE;
	GUID guid;

	hResult = CLSIDFromString(OVERLAY_GUID, (LPCLSID)&guid);

	if (hResult != S_OK)
	{
		return hResult;
	}

	if (!IsEqualCLSID(guid, rclsid))
	{
		return hResult;
	}

	hResult = E_OUTOFMEMORY;

	wchar_t szModule[MAX_PATH];

	if (GetModuleFileName(instanceHandle, szModule, ARRAYSIZE(szModule)) == 0)
	{
		hResult = HRESULT_FROM_WIN32(GetLastError());

		return hResult;
	}

	DriveOverlayFactory* driveOverlayFactory = new DriveOverlayFactory(szModule);

	if (driveOverlayFactory)
	{
		hResult = driveOverlayFactory->QueryInterface(riid, ppv);
		driveOverlayFactory->Release();
	}
	return hResult;
}

STDAPI DllCanUnloadNow(void)
{
	return dllReferenceCount > 0 ? S_FALSE : S_OK;

	return S_FALSE;
}

HRESULT _stdcall DllRegisterServer(void)
{
	HRESULT hResult = S_OK;

	wchar_t szModule[MAX_PATH];

	if (GetModuleFileName(instanceHandle, szModule, ARRAYSIZE(szModule)) == 0)
	{
		hResult = HRESULT_FROM_WIN32(GetLastError());

		return hResult;
	}

	GUID guid;

	hResult = CLSIDFromString(OVERLAY_GUID, (LPCLSID)&guid);

	if (hResult != S_OK)
	{
		return hResult;
	}

	hResult = DriveOverlayRegistrationHandler::RegisterCOMObject(szModule, guid);

	if (FAILED(hResult))
	{
		return hResult;
	}

	hResult = DriveOverlayRegistrationHandler::MakeRegistryEntries(guid, OVERLAY_NAME);

	if (FAILED(hResult))
	{
		return hResult;
	}

	return hResult;
}

STDAPI DllUnregisterServer(void)
{
	HRESULT hResult = S_OK;

	wchar_t szModule[MAX_PATH];

	if (GetModuleFileNameW(instanceHandle, szModule, ARRAYSIZE(szModule)) == 0)
	{
		hResult = HRESULT_FROM_WIN32(GetLastError());
		return hResult;
	}

	GUID guid;

	hResult = CLSIDFromString(OVERLAY_GUID, (LPCLSID)&guid);

	if (hResult != S_OK)
	{
		return hResult;
	}

	hResult = DriveOverlayRegistrationHandler::UnregisterCOMObject(guid);

	if (FAILED(hResult))
	{
		return hResult;
	}

	hResult = DriveOverlayRegistrationHandler::RemoveRegistryEntries(OVERLAY_NAME);

	if (FAILED(hResult))
	{
		return hResult;
	}

	return hResult;
}
