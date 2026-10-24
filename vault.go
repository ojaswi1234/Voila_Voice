package main

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"fmt"
	"io"
	"log"
	"sync"
	"time"
)

// zeroBytes overwrites a sensitive byte slice with zeroes to remove it from memory
func zeroBytes(b []byte) {
	for i := range b {
		b[i] = 0
	}
}

// EncryptedCredItem holds credentials encrypted in RAM with AES-256-GCM
type EncryptedCredItem struct {
	ID         string
	Provider   string // ollama, groq, github
	Model      string
	BaseURL    string
	Ciphertext []byte
	Nonce      []byte
	CachedAt   time.Time
	ExpiresAt  time.Time
	LastUsedAt time.Time
}

// FlipperPolicy defines user-governed toggles, timeslot windows, and auto-destroy behavior
type FlipperPolicy struct {
	MasterEnabled       bool   `json:"master_enabled"`
	WatchdogEnabled     bool   `json:"watchdog_enabled"`
	ClipboardEnabled    bool   `json:"clipboard_enabled"`
	BriefingEnabled     bool   `json:"briefing_enabled"`
	NightlyAuditEnabled bool   `json:"nightly_audit_enabled"`
	TimeslotsEnabled    bool   `json:"timeslots_enabled"`
	MorningSlotStart    int    `json:"morning_slot_start"`
	MorningSlotEnd      int    `json:"morning_slot_end"`
	EveningSlotStart    int    `json:"evening_slot_start"`
	EveningSlotEnd      int    `json:"evening_slot_end"`
	NightlySlotStart    int    `json:"nightly_slot_start"`
	NightlySlotEnd      int    `json:"nightly_slot_end"`
	MaxKeyTTLMinutes    int    `json:"max_key_ttl_minutes"`
	Status              string `json:"status"` // active, dormant, deactivated
}

// EphemeralVault manages in-memory encrypted credentials with an auto-destroyer
type EphemeralVault struct {
	mu        sync.RWMutex
	masterKey []byte
	items     map[string]*EncryptedCredItem
	policy    FlipperPolicy
	stopChan  chan struct{}
}

var globalVault = NewEphemeralVault()

func generateRandomKey(size int) []byte {
	k := make([]byte, size)
	if _, err := io.ReadFull(rand.Reader, k); err != nil {
		panic("crypto/rand failure: unable to generate vault master key")
	}
	return k
}

// NewEphemeralVault initializes the vault with a dynamic in-memory master key
func NewEphemeralVault() *EphemeralVault {
	v := &EphemeralVault{
		masterKey: generateRandomKey(32), // 256-bit AES key in memory
		items:     make(map[string]*EncryptedCredItem),
		stopChan:  make(chan struct{}),
		policy: FlipperPolicy{
			MasterEnabled:       true,
			WatchdogEnabled:     true,
			ClipboardEnabled:    true,
			BriefingEnabled:     true,
			NightlyAuditEnabled: true,
			TimeslotsEnabled:    true,
			MorningSlotStart:    8,  // 8:00 AM
			MorningSlotEnd:      10, // 10:00 AM
			EveningSlotStart:    18, // 6:00 PM
			EveningSlotEnd:      20, // 8:00 PM
			NightlySlotStart:    2,  // 2:00 AM
			NightlySlotEnd:      3,  // 3:00 AM
			MaxKeyTTLMinutes:    30, // 30 minutes idle TTL
			Status:              "active",
		},
	}
	v.startAutoDestroyer()
	return v
}

// StoreCred encrypts plaintext in memory with AES-256-GCM and stores it with TTL
func (v *EphemeralVault) StoreCred(id, provider, model, baseURL, secret string, ttl time.Duration) error {
	v.mu.Lock()
	defer v.mu.Unlock()

	block, err := aes.NewCipher(v.masterKey)
	if err != nil {
		return fmt.Errorf("aes cipher error: %w", err)
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return fmt.Errorf("gcm error: %w", err)
	}

	nonce := make([]byte, gcm.NonceSize())
	if _, err := io.ReadFull(rand.Reader, nonce); err != nil {
		return fmt.Errorf("nonce read error: %w", err)
	}

	secretBytes := []byte(secret)
	ciphertext := gcm.Seal(nil, nonce, secretBytes, nil)
	zeroBytes(secretBytes) // Zero input secret immediately

	if ttl <= 0 {
		ttl = time.Duration(v.policy.MaxKeyTTLMinutes) * time.Minute
		if ttl <= 0 {
			ttl = 30 * time.Minute
		}
	}

	// If replacing existing item, wipe old data first
	if old, exists := v.items[id]; exists {
		zeroBytes(old.Ciphertext)
		zeroBytes(old.Nonce)
	}

	now := time.Now()
	v.items[id] = &EncryptedCredItem{
		ID:         id,
		Provider:   provider,
		Model:      model,
		BaseURL:    baseURL,
		Ciphertext: ciphertext,
		Nonce:      nonce,
		CachedAt:   now,
		ExpiresAt:  now.Add(ttl),
		LastUsedAt: now,
	}

	v.policy.Status = "active"
	log.Printf("[Ephemeral Vault] Stored credential '%s' (Provider: %s, TTL: %v)", id, provider, ttl)
	return nil
}

// BorrowCred securely decrypts the secret, calls fn, and guarantees zeroing plaintext on return
func (v *EphemeralVault) BorrowCred(id string, fn func(plaintext []byte, provider, model, baseURL string) error) error {
	v.mu.Lock()
	item, exists := v.items[id]
	if !exists {
		v.mu.Unlock()
		return fmt.Errorf("credential '%s' not found or expired", id)
	}

	if time.Now().After(item.ExpiresAt) {
		zeroBytes(item.Ciphertext)
		zeroBytes(item.Nonce)
		delete(v.items, id)
		v.mu.Unlock()
		return fmt.Errorf("credential '%s' has expired", id)
	}

	// Update activity timestamp & extend TTL slightly
	item.LastUsedAt = time.Now()
	item.ExpiresAt = time.Now().Add(time.Duration(v.policy.MaxKeyTTLMinutes) * time.Minute)

	block, err := aes.NewCipher(v.masterKey)
	if err != nil {
		v.mu.Unlock()
		return fmt.Errorf("aes cipher error: %w", err)
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		v.mu.Unlock()
		return fmt.Errorf("gcm error: %w", err)
	}

	plaintext, err := gcm.Open(nil, item.Nonce, item.Ciphertext, nil)
	if err != nil {
		v.mu.Unlock()
		return fmt.Errorf("gcm open error: %w", err)
	}
	prov := item.Provider
	mod := item.Model
	bURL := item.BaseURL
	v.mu.Unlock()

	// Guarantee zero-wiping plaintext as soon as borrowed window closes
	defer zeroBytes(plaintext)

	return fn(plaintext, prov, mod, bURL)
}

// HasCred checks if an active credential exists without decrypting it
func (v *EphemeralVault) HasCred(id string) bool {
	v.mu.RLock()
	defer v.mu.RUnlock()
	item, exists := v.items[id]
	if !exists {
		return false
	}
	return time.Now().Before(item.ExpiresAt)
}

// IsActionAllowed checks toggles and preset timeslots
func (v *EphemeralVault) IsActionAllowed(toolType string) (bool, string) {
	v.mu.RLock()
	defer v.mu.RUnlock()

	if !v.policy.MasterEnabled {
		return false, "Flipper cloud execution is disabled by master switch"
	}

	switch toolType {
	case "watchdog":
		if !v.policy.WatchdogEnabled {
			return false, "Terminal & build watchdog is disabled by user policy"
		}
	case "clipboard":
		if !v.policy.ClipboardEnabled {
			return false, "Clipboard error interceptor is disabled by user policy"
		}
	case "briefing":
		if !v.policy.BriefingEnabled {
			return false, "Morning briefing is disabled by user policy"
		}
	case "nightly_audit":
		if !v.policy.NightlyAuditEnabled {
			return false, "Nightly maintenance guardian is disabled by user policy"
		}
	}

	if v.policy.TimeslotsEnabled {
		hour := time.Now().Hour()
		inMorning := hour >= v.policy.MorningSlotStart && hour < v.policy.MorningSlotEnd
		inEvening := hour >= v.policy.EveningSlotStart && hour < v.policy.EveningSlotEnd
		inNightly := hour >= v.policy.NightlySlotStart && hour < v.policy.NightlySlotEnd

		if !inMorning && !inEvening && !inNightly {
			return false, fmt.Sprintf("Outside preset active timeslots (Current hour: %d). System is in dormant state.", hour)
		}
	}

	return true, "ok"
}

// DestroyAllAndDeactivate zeroes all cached credentials, rolls a new master key, and marks deactivated
func (v *EphemeralVault) DestroyAllAndDeactivate() {
	v.mu.Lock()
	defer v.mu.Unlock()

	for _, item := range v.items {
		zeroBytes(item.Ciphertext)
		zeroBytes(item.Nonce)
	}
	v.items = make(map[string]*EncryptedCredItem)

	// Re-roll master key to ensure memory garbage collection cannot decrypt anything
	zeroBytes(v.masterKey)
	v.masterKey = generateRandomKey(32)

	v.policy.Status = "deactivated"
	log.Printf("[Ephemeral Vault] 🧹 All credentials securely zero-wiped. Vault deactivated.")
}

// PanicDestroyAll immediately destroys everything in memory during a security breach
func (v *EphemeralVault) PanicDestroyAll() {
	v.mu.Lock()
	defer v.mu.Unlock()

	log.Printf("[SECURITY BREACH TRIGGER] Panic destroying all ephemeral vault keys!")
	for _, item := range v.items {
		zeroBytes(item.Ciphertext)
		zeroBytes(item.Nonce)
	}
	v.items = make(map[string]*EncryptedCredItem)
	zeroBytes(v.masterKey)
	v.masterKey = generateRandomKey(32)
	v.policy.Status = "panic_locked"
}

// UpdatePolicy updates the policy safely
func (v *EphemeralVault) UpdatePolicy(newPolicy FlipperPolicy) {
	v.mu.Lock()
	defer v.mu.Unlock()
	v.policy = newPolicy
	log.Printf("[Ephemeral Vault] Updated Flipper policy: Master=%t, Timeslots=%t, Status=%s", newPolicy.MasterEnabled, newPolicy.TimeslotsEnabled, newPolicy.Status)
}

// GetPolicyStatus returns a safe JSON status map (NO secrets exposed)
func (v *EphemeralVault) GetPolicyStatus() map[string]interface{} {
	v.mu.RLock()
	defer v.mu.RUnlock()

	activeCreds := []string{}
	now := time.Now()
	for id, item := range v.items {
		if now.Before(item.ExpiresAt) {
			activeCreds = append(activeCreds, fmt.Sprintf("%s (%s, expires in %ds)", id, item.Provider, int(item.ExpiresAt.Sub(now).Seconds())))
		}
	}

	hour := now.Hour()
	inSlot := true
	if v.policy.TimeslotsEnabled {
		inMorning := hour >= v.policy.MorningSlotStart && hour < v.policy.MorningSlotEnd
		inEvening := hour >= v.policy.EveningSlotStart && hour < v.policy.EveningSlotEnd
		inNightly := hour >= v.policy.NightlySlotStart && hour < v.policy.NightlySlotEnd
		inSlot = inMorning || inEvening || inNightly
	}

	status := v.policy.Status
	if !v.policy.MasterEnabled {
		status = "disabled"
	} else if len(activeCreds) == 0 {
		status = "keys_empty"
	} else if !inSlot {
		status = "dormant_timeslot"
	}

	return map[string]interface{}{
		"type":                 "flipper_policy_status",
		"status":               status,
		"master_enabled":       v.policy.MasterEnabled,
		"watchdog_enabled":     v.policy.WatchdogEnabled,
		"clipboard_enabled":    v.policy.ClipboardEnabled,
		"briefing_enabled":     v.policy.BriefingEnabled,
		"nightly_audit_enabled": v.policy.NightlyAuditEnabled,
		"timeslots_enabled":    v.policy.TimeslotsEnabled,
		"in_active_timeslot":   inSlot,
		"current_hour":         hour,
		"morning_slot":         fmt.Sprintf("%02d:00 - %02d:00", v.policy.MorningSlotStart, v.policy.MorningSlotEnd),
		"evening_slot":         fmt.Sprintf("%02d:00 - %02d:00", v.policy.EveningSlotStart, v.policy.EveningSlotEnd),
		"nightly_slot":         fmt.Sprintf("%02d:00 - %02d:00", v.policy.NightlySlotStart, v.policy.NightlySlotEnd),
		"cached_credentials":   activeCreds,
	}
}

// startAutoDestroyer runs a periodic background sweeper every 20 seconds
func (v *EphemeralVault) startAutoDestroyer() {
	go func() {
		ticker := time.NewTicker(20 * time.Second)
		defer ticker.Stop()

		for {
			select {
			case <-v.stopChan:
				return
			case <-ticker.C:
				v.mu.Lock()
				now := time.Now()
				hour := now.Hour()

				// If timeslots enabled and outside all windows, wipe keys to prevent lingering secrets
				outsideSlots := false
				if v.policy.TimeslotsEnabled {
					inMorning := hour >= v.policy.MorningSlotStart && hour < v.policy.MorningSlotEnd
					inEvening := hour >= v.policy.EveningSlotStart && hour < v.policy.EveningSlotEnd
					inNightly := hour >= v.policy.NightlySlotStart && hour < v.policy.NightlySlotEnd
					outsideSlots = !inMorning && !inEvening && !inNightly
				}

				for id, item := range v.items {
					// Expire if TTL reached OR if outside preset timeslots
					if now.After(item.ExpiresAt) || outsideSlots {
						zeroBytes(item.Ciphertext)
						zeroBytes(item.Nonce)
						delete(v.items, id)
						log.Printf("[Ephemeral Vault Auto-Destroyer] ⏱️ Wiped expired credential '%s' (OutsideSlot=%t)", id, outsideSlots)
					}
				}

				if outsideSlots && v.policy.Status == "active" {
					v.policy.Status = "dormant"
				}
				v.mu.Unlock()
			}
		}
	}()
}
