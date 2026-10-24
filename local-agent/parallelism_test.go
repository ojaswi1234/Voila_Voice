package main

import (
	"context"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestTokenBucketLimiter(t *testing.T) {
	limiter := NewTokenBucketLimiter(10.0, 5.0)

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	// Should immediately take up to burst capacity
	for i := 0; i < 5; i++ {
		err := limiter.Wait(ctx, 1.0)
		if err != nil {
			t.Fatalf("Expected immediate acquisition of token %d, got error: %v", i, err)
		}
	}

	// 6th token must wait ~100ms
	start := time.Now()
	err := limiter.Wait(ctx, 1.0)
	elapsed := time.Since(start)
	if err != nil {
		t.Fatalf("Expected 6th token after waiting, got error: %v", err)
	}
	if elapsed < 50*time.Millisecond {
		t.Errorf("Expected wait time >= 50ms, got %v", elapsed)
	}
}

func TestGetAllBrainDirsExcludesAntigravity(t *testing.T) {
	dirs := getAllBrainDirs()
	for _, d := range dirs {
		if filepath.Base(filepath.Dir(d)) == "antigravity-cli" {
			t.Errorf("getAllBrainDirs() must NOT contain antigravity-cli brain dir: %s", d)
		}
	}
}

func TestPinAndForkConversationInternal(t *testing.T) {
	testConvID := "test_conv_parallel_01"
	
	// Ensure cleanup
	brainDir := getBrainDir()
	testDir := filepath.Join(brainDir, testConvID)
	defer os.RemoveAll(testDir)

	// Test Pin
	ok := pinConversationInternal(testConvID, true)
	if !ok {
		t.Fatalf("pinConversationInternal failed")
	}

	meta, found := loadConversationMetadata(testConvID)
	if !found {
		t.Fatalf("Expected metadata to exist after pin")
	}
	if !meta.IsPinned {
		t.Errorf("Expected IsPinned == true, got false")
	}

	// Test Fork
	forkID := "test_conv_parallel_01_forked"
	defer os.RemoveAll(filepath.Join(brainDir, forkID))

	forkOk := forkConversationInternal(testConvID, forkID, "GROQ")
	if !forkOk {
		t.Fatalf("forkConversationInternal failed")
	}

	forkMeta, forkFound := loadConversationMetadata(forkID)
	if !forkFound {
		t.Fatalf("Expected fork metadata to exist")
	}
	if forkMeta.ParentID != testConvID {
		t.Errorf("Expected ParentID == %s, got %s", testConvID, forkMeta.ParentID)
	}
	if forkMeta.ModelType != "GROQ" {
		t.Errorf("Expected ModelType == GROQ, got %s", forkMeta.ModelType)
	}
}
