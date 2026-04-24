package main

import (
	"fmt"
	"testing"
)

// Simple function
func simpleFunction() string {
	return "Hello, World!"
}

// Function with generics
func Map[T any, U any](slice []T, f func(T) U) []U {
	result := make([]U, len(slice))
	for i, v := range slice {
		result[i] = f(v)
	}
	return result
}

// Struct definition
type User struct {
	ID    int
	Name  string
	Email string
}

// Generic struct
type Stack[T any] struct {
	items []T
}

// Interface definition
type Repository interface {
	Find(id int) (interface{}, error)
	Save(entity interface{}) error
}

// Method with pointer receiver
func (u *User) String() string {
	return fmt.Sprintf("%s <%s>", u.Name, u.Email)
}

// Method on generic type
func (s *Stack[T]) Push(item T) {
	s.items = append(s.items, item)
}

// Const block with iota
const (
	StatusPending  Status = iota
	StatusActive
	StatusInactive
)

// Type alias
type Status int

// Init function
func init() {
	fmt.Println("Initializing...")
}

// Test function
func TestSimpleFunction(t *testing.T) {
	result := simpleFunction()
	if result != "Hello, World!" {
		t.Errorf("expected Hello, World!, got %s", result)
	}
}
