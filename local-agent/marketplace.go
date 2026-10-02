package main

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"sync"
	"time"
)

type InstalledSkill struct {
	ID          string `json:"id"`
	Name        string `json:"name"`
	Description string `json:"description"`
	Source      string `json:"source"`
	Hash        string `json:"hash"`
	InstalledAt string `json:"installed_at"`
}

type SkillMarketItem struct {
	ID          string `json:"id"`
	Name        string `json:"name"`
	Description string `json:"description"`
	Source      string `json:"source"`
}

type SkillIndex struct {
	Installed []InstalledSkill `json:"installed"`
}

var installMutex sync.Map

func loadSkillIndex() ([]InstalledSkill, error) {
	data, err := os.ReadFile(filepath.Join("skills", "index.json"))
	if err != nil {
		if os.IsNotExist(err) {
			return []InstalledSkill{}, nil
		}
		return nil, err
	}
	var idx SkillIndex
	if err := json.Unmarshal(data, &idx); err != nil {
		return nil, err
	}
	if idx.Installed == nil {
		return []InstalledSkill{}, nil
	}
	return idx.Installed, nil
}

func saveSkillIndex(installed []InstalledSkill) error {
	idx := SkillIndex{Installed: installed}
	if idx.Installed == nil {
		idx.Installed = []InstalledSkill{}
	}
	data, err := json.MarshalIndent(idx, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(filepath.Join("skills", "index.json"), data, 0644)
}

func skillsMarketSearch(query string) ([]SkillMarketItem, error) {
	url := fmt.Sprintf("https://api.github.com/search/repositories?q=%s+in:readme+SKILL.md", query)
	resp, err := http.Get(url)
	if err != nil {
		return []SkillMarketItem{}, nil
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		return []SkillMarketItem{}, nil
	}
	var result struct {
		Items []struct {
			Name        string `json:"name"`
			Description string `json:"description"`
			HtmlUrl     string `json:"html_url"`
		} `json:"items"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return []SkillMarketItem{}, nil
	}
	var items []SkillMarketItem
	for _, item := range result.Items {
		items = append(items, SkillMarketItem{
			ID:          item.Name,
			Name:        item.Name,
			Description: item.Description,
			Source:      item.HtmlUrl,
		})
	}
	return items, nil
}

func logAudit(msg string) {
	f, err := os.OpenFile("security_audit.jsonl", os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err == nil {
		defer f.Close()
		f.WriteString(fmt.Sprintf("{\"timestamp\":\"%s\",\"action\":\"marketplace\",\"details\":\"%s\"}\n", time.Now().Format(time.RFC3339), msg))
	}
}

func validateID(id string) bool {
	if id == "" { return false }
	match, _ := regexp.MatchString("^[a-zA-Z0-9_-]+$", id)
	if !match {
		return false
	}
	if strings.Contains(id, ".") || strings.Contains(id, "/") || strings.Contains(id, "\\") {
		return false
	}
	return true
}

func skillsMarketInstall(id, source string) (string, error) {
	if !validateID(id) {
		return "", fmt.Errorf("invalid id")
	}
	if !strings.HasPrefix(source, "https://") {
		return "", fmt.Errorf("source must be https://")
	}

	_, loaded := installMutex.LoadOrStore(id, true)
	if loaded {
		return "", fmt.Errorf("installation of %s already in progress", id)
	}
	defer installMutex.Delete(id)

	resp, err := http.Get(source)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		return "", fmt.Errorf("failed to download skill: %s", resp.Status)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}

	installDir := filepath.Join("skills", "installed", id)
	basePath, _ := filepath.Abs(filepath.Join("skills", "installed"))
	targetPath, _ := filepath.Abs(installDir)
	rel, err := filepath.Rel(basePath, targetPath)
	if err != nil || strings.HasPrefix(rel, "..") {
		return "", fmt.Errorf("invalid path traversal")
	}

	bodyStr := string(body)
	if !strings.Contains(bodyStr, "# ") {
		return "", fmt.Errorf("invalid SKILL.md: missing markdown header")
	}

	if err := os.MkdirAll(installDir, 0755); err != nil {
		return "", err
	}

	skillPath := filepath.Join(installDir, "SKILL.md")
	if err := os.WriteFile(skillPath, body, 0644); err != nil {
		return "", err
	}


	installed, err := loadSkillIndex()
	if err != nil {
		return "", err
	}
	
	found := false
	for i, s := range installed {
		if s.ID == id {
			installed[i].Source = source
			installed[i].InstalledAt = time.Now().Format(time.RFC3339)
			found = true
			break
		}
	}
	if !found {
		installed = append(installed, InstalledSkill{
			ID:          id,
			Name:        id,
			Source:      source,
			InstalledAt: time.Now().Format(time.RFC3339),
		})
	}
	if err := saveSkillIndex(installed); err != nil {
		return "", err
	}

	logAudit(fmt.Sprintf("Installed skill %s from %s", id, source))
	return "success", nil
}

func skillsMarketUninstall(id string) error {
	if !validateID(id) {
		return fmt.Errorf("invalid id")
	}
	installed, err := loadSkillIndex()
	if err != nil {
		return err
	}
	
	var newInstalled []InstalledSkill
	for _, s := range installed {
		if s.ID != id {
			newInstalled = append(newInstalled, s)
		}
	}
	
	if err := saveSkillIndex(newInstalled); err != nil {
		return err
	}
	
	installDir := filepath.Join("skills", "installed", id)
	os.RemoveAll(installDir)
	
	logAudit(fmt.Sprintf("Uninstalled skill %s", id))
	return nil
}

func skillsMarketListInstalled() ([]InstalledSkill, error) {
	return loadSkillIndex()
}
