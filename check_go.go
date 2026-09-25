package main
import (
	"fmt"
	"os"
	"bytes"
)
func main() {
	b, _ := os.ReadFile("local-agent/main.go")
	if bytes.Contains(b, []byte("content.WriteString(\"\\\\n\\\\n\")")) {
		fmt.Println("Found DOUBLE backslash")
	} else if bytes.Contains(b, []byte("content.WriteString(\"\\n\\n\")")) {
		fmt.Println("Found SINGLE backslash")
	} else {
		fmt.Println("Found NEITHER")
	}
}
