//go:build windows
// +build windows

package main

import (
	"syscall"
	"time"
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
	procSetThreadExecutionState.Call(uintptr(esContinuous | esSystemRequired))
}

func wakeScreen() {
	procSetThreadExecutionState.Call(uintptr(esContinuous | esSystemRequired | esDisplayRequired))
	time.AfterFunc(2*time.Second, func() {
		procSetThreadExecutionState.Call(uintptr(esContinuous | esSystemRequired))
	})
}
