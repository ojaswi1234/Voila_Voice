package main

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"errors"
	"io"

	"golang.org/x/crypto/pbkdf2"
)

// saltSize bytes of random salt are prepended to every ciphertext blob.
const saltSize = 16

// pbkdf2Iterations: NIST recommends >=100k for PBKDF2-SHA256 (2023 guidance).
// At 100k iterations a modern GPU takes ~0.3 seconds per guess vs ~0.0001ms for bare SHA-256.
const pbkdf2Iterations = 100_000

// deriveKey stretches a human passphrase into a 256-bit AES key via PBKDF2-SHA256.
// Bug #19 Fix: replaces the former sha256.Sum256(passphrase) single-hash which
// was trivially brute-forceable at billions of guesses per second on commodity GPUs.
func deriveKey(passphrase string, salt []byte) []byte {
	return pbkdf2.Key([]byte(passphrase), salt, pbkdf2Iterations, 32, sha256.New)
}

// EncryptData encrypts data with AES-256-GCM.
// Output wire format (base64-encoded): salt[16] | nonce[12] | ciphertext+tag
func EncryptData(data []byte, passphrase string) (string, error) {
	salt := make([]byte, saltSize)
	if _, err := io.ReadFull(rand.Reader, salt); err != nil {
		return "", err
	}

	key := deriveKey(passphrase, salt)
	block, err := aes.NewCipher(key)
	if err != nil {
		return "", err
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return "", err
	}
	nonce := make([]byte, gcm.NonceSize())
	if _, err = io.ReadFull(rand.Reader, nonce); err != nil {
		return "", err
	}

	ciphertext := gcm.Seal(nonce, nonce, data, nil)
	blob := append(salt, ciphertext...)
	return base64.StdEncoding.EncodeToString(blob), nil
}

// DecryptData decrypts data produced by EncryptData.
func DecryptData(encryptedBase64 string, passphrase string) ([]byte, error) {
	blob, err := base64.StdEncoding.DecodeString(encryptedBase64)
	if err != nil {
		return nil, err
	}
	if len(blob) < saltSize {
		return nil, errors.New("ciphertext too short (missing salt)")
	}

	salt := blob[:saltSize]
	rest := blob[saltSize:]

	key := deriveKey(passphrase, salt)
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, err
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, err
	}
	nonceSize := gcm.NonceSize()
	if len(rest) < nonceSize {
		return nil, errors.New("ciphertext too short (missing nonce)")
	}
	nonce, ciphertext := rest[:nonceSize], rest[nonceSize:]
	return gcm.Open(nil, nonce, ciphertext, nil)
}
