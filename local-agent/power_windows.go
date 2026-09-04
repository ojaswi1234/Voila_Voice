//go:build windows
// +build windows

package main

import (
	"runtime"
	"syscall"
)

var (
	kernel32 = syscall.NewLazyDLL("kernel32.dll")
	procSetThreadExecutionState = kernel32.NewProc("SetThreadExecutionState")
)

const (
	esSystemRequired  = 0x00000001
	esDisplayRequired = 0x00000002
	esContinuous      = 0x80000000
)

func keepSystemAwake() {
	go func() {
		// SetThreadExecutionState applies to the calling thread. 
		// If the thread dies, Windows revokes the awake state.
		// We lock this OS thread and keep it alive forever to prevent sleep.
		runtime.LockOSThread()
		procSetThreadExecutionState.Call(uintptr(esContinuous | esSystemRequired))
		select {} // Block forever
	}()
}

func wakeScreen() {
	// To merely wake the screen / reset the idle timer, we do NOT use esContinuous.
	// Calling it without esContinuous simulates user activity instantly.
	procSetThreadExecutionState.Call(uintptr(esSystemRequired | esDisplayRequired))
}
