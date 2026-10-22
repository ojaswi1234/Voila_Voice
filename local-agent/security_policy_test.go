package main

import "testing"

func TestTerminalPolicy(t *testing.T) {
	if EvaluateTerminalCommand("dir").Level != PolicyAllow { t.Error("dir should allow") }
	if EvaluateTerminalCommand("format c:").Level != PolicyDeny { t.Error("format c: should deny") }
	if EvaluateTerminalCommand("net user").Level != PolicyApprove { t.Error("net user should approve") }
	if EvaluateTerminalCommand("git push").Level != PolicyAllow { t.Error("git push should allow") }
}

func TestDesktopPolicy(t *testing.T) {
	if EvaluateDesktopAction("snapshot", "", "", "", "MyApp", "", "", "").Level != PolicyAllow { t.Error("snapshot allow") }
	if EvaluateDesktopAction("click_ref", "e1", "", "", "User Account Control", "Yes", "", "").Level != PolicyApprove { 
		t.Error("UAC should be approve")
	}
	if EvaluateDesktopAction("type_keys", "", "", "hello", "Notepad", "", "", "").Level != PolicyAllow { t.Error("hello allow") }
	if EvaluateDesktopAction("type_keys", "", "", "diskpart", "Notepad", "", "", "").Level != PolicyApprove { t.Error("diskpart approve") }
}

func TestBrowserPolicy(t *testing.T) {
	// 1. Checkout URLs denied
	if EvaluateBrowserAction("goto", "https://checkout.stripe.com/pay/123", "", "").Level != PolicyDeny {
		t.Error("stripe checkout goto should deny")
	}
	if EvaluateBrowserAction("goto", "https://amazon.com/cart/checkout", "", "").Level != PolicyDeny {
		t.Error("cart checkout goto should deny")
	}
	// Safe URLs allowed
	if EvaluateBrowserAction("goto", "https://example.com/docs", "", "").Level != PolicyAllow {
		t.Error("example.com goto should allow")
	}

	// 2. Payment CTA clicks denied
	if EvaluateBrowserAction("click", "", "role=button[name='Pay now']", "").Level != PolicyDeny {
		t.Error("click Pay now should deny")
	}
	if EvaluateBrowserAction("click", "", "button#place-order", "Place Order").Level != PolicyDeny {
		t.Error("click Place order should deny")
	}
	if EvaluateBrowserAction("click", "", "role=button[name='Search']", "").Level != PolicyAllow {
		t.Error("click Search button should allow")
	}

	// 3. Payment fields denied
	if EvaluateBrowserAction("type", "", "input[name='cc-number']", "1234").Level != PolicyDeny {
		t.Error("type into cc-number should deny")
	}
	if EvaluateBrowserAction("type", "", "input#cvv", "123").Level != PolicyDeny {
		t.Error("type into cvv should deny")
	}
	if EvaluateBrowserAction("type", "", "input[name='q']", "golang testing").Level != PolicyAllow {
		t.Error("type search query should allow")
	}

	// 4. PAN card number in value denied
	if EvaluateBrowserAction("type", "", "input#field", "4111222233334444").Level != PolicyDeny {
		t.Error("type with 16-digit PAN should deny")
	}

	// 5. MaskPAN helper
	masked := MaskPAN("Card is 4111222233334444 and cvv is 123")
	if masked != "Card is ************4444 and cvv is 123" {
		t.Errorf("MaskPAN failed: got %s", masked)
	}
}
