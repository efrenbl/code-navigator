"""Tests for Ruby analyzer."""

from pathlib import Path

import pytest

from codenav.code_navigator import GenericAnalyzer
from codenav.ruby_analyzer import TREE_SITTER_AVAILABLE, RubyAnalyzer

FIXTURES_DIR = Path(__file__).parent / "fixtures"
RB_FIXTURE = FIXTURES_DIR / "sample_ruby.rb"


class TestTreeSitterAvailability:
    def test_tree_sitter_flag_is_boolean(self):
        assert isinstance(TREE_SITTER_AVAILABLE, bool)

    def test_can_import_analyzer_regardless_of_tree_sitter(self):
        assert RubyAnalyzer is not None


class TestRubyAnalyzer:
    @pytest.fixture
    def rb_source(self):
        return RB_FIXTURE.read_text()

    def test_analyze_returns_symbols(self, rb_source):
        analyzer = RubyAnalyzer("sample_ruby.rb", rb_source)
        symbols = analyzer.analyze()
        assert len(symbols) > 0

    def test_detect_class(self, rb_source):
        analyzer = RubyAnalyzer("sample_ruby.rb", rb_source)
        symbols = analyzer.analyze()
        classes = [s for s in symbols if s.type == "class"]
        names = [s.name for s in classes]
        assert "SimpleClass" in names
        assert "DerivedClass" in names

    def test_detect_module(self, rb_source):
        analyzer = RubyAnalyzer("sample_ruby.rb", rb_source)
        symbols = analyzer.analyze()
        modules = [s for s in symbols if s.type == "module"]
        names = [s.name for s in modules]
        assert "Validators" in names

    def test_detect_method(self, rb_source):
        analyzer = RubyAnalyzer("sample_ruby.rb", rb_source)
        symbols = analyzer.analyze()
        names = [s.name for s in symbols]
        assert "initialize" in names
        assert "get_value" in names

    def test_detect_top_level_function(self, rb_source):
        analyzer = RubyAnalyzer("sample_ruby.rb", rb_source)
        symbols = analyzer.analyze()
        funcs = [s for s in symbols if s.name == "greet"]
        assert len(funcs) == 1
        assert funcs[0].type == "function"

    def test_detect_class_inheritance(self, rb_source):
        analyzer = RubyAnalyzer("sample_ruby.rb", rb_source)
        symbols = analyzer.analyze()
        derived = next(s for s in symbols if s.name == "DerivedClass")
        assert "SimpleClass" in (derived.signature or "")

    def test_symbol_has_line_numbers(self, rb_source):
        analyzer = RubyAnalyzer("sample_ruby.rb", rb_source)
        symbols = analyzer.analyze()
        for s in symbols:
            assert s.line_start > 0
            assert s.line_end >= s.line_start

    def test_empty_source(self):
        analyzer = RubyAnalyzer("empty.rb", "")
        symbols = analyzer.analyze()
        assert symbols == []

    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="parent tracking requires tree-sitter")
    def test_method_parent_class(self, rb_source):
        analyzer = RubyAnalyzer("sample_ruby.rb", rb_source)
        symbols = analyzer.analyze()
        get_value = next(s for s in symbols if s.name == "get_value")
        assert get_value.parent == "SimpleClass"


class TestRubyAnalyzerInlineExamples:
    def test_simple_method(self):
        source = """
def hello(name)
  "Hello, #{name}!"
end
"""
        analyzer = RubyAnalyzer("test.rb", source)
        symbols = analyzer.analyze()
        assert len(symbols) >= 1
        assert symbols[0].name == "hello"

    def test_class_with_methods(self):
        source = """
class Dog
  def bark
    "Woof!"
  end

  def fetch(item)
    "Fetching #{item}"
  end
end
"""
        analyzer = RubyAnalyzer("test.rb", source)
        symbols = analyzer.analyze()
        names = [s.name for s in symbols]
        assert "Dog" in names
        assert "bark" in names
        assert "fetch" in names

    def test_module_with_class(self):
        source = """
module Animals
  class Cat
    def meow
      "Meow!"
    end
  end
end
"""
        analyzer = RubyAnalyzer("test.rb", source)
        symbols = analyzer.analyze()
        names = [s.name for s in symbols]
        assert "Animals" in names
        assert "Cat" in names
        assert "meow" in names

    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="special chars require tree-sitter")
    def test_method_with_special_chars(self):
        source = """
class Checker
  def valid?
    true
  end

  def save!
    true
  end
end
"""
        analyzer = RubyAnalyzer("test.rb", source)
        symbols = analyzer.analyze()
        names = [s.name for s in symbols]
        assert "valid?" in names
        assert "save!" in names

    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="singleton methods require tree-sitter")
    def test_singleton_method(self):
        source = """
class Factory
  def self.create(type)
    new(type)
  end
end
"""
        analyzer = RubyAnalyzer("test.rb", source)
        symbols = analyzer.analyze()
        create = next(s for s in symbols if s.name == "create")
        assert "self." in (create.signature or "")


class TestRubyFallbackBehavior:
    def test_ruby_fallback_produces_symbols(self):
        source = """
class MyClass
  def hello
    "world"
  end
end
"""
        fallback = GenericAnalyzer("test.rb", source, "ruby")
        symbols = fallback.analyze()
        assert len(symbols) > 0
        names = [s.name for s in symbols]
        assert "MyClass" in names
        assert "hello" in names

    def test_ruby_end_detection(self):
        source = """
def outer
  if true
    puts "hi"
  end
  42
end
"""
        fallback = GenericAnalyzer("test.rb", source, "ruby")
        symbols = fallback.analyze()
        func = next((s for s in symbols if s.name == "outer"), None)
        assert func is not None
        assert func.line_end > func.line_start + 2

    def test_ruby_module_fallback(self):
        source = """
module MyMod
  def helper
    true
  end
end
"""
        fallback = GenericAnalyzer("test.rb", source, "ruby")
        symbols = fallback.analyze()
        names = [s.name for s in symbols]
        assert "MyMod" in names
        assert "helper" in names


class TestRubyEdgeCases:
    def test_syntax_error_handling(self):
        source = "def broken(\nend end end"
        analyzer = RubyAnalyzer("bad.rb", source)
        # Should not raise
        symbols = analyzer.analyze()
        assert isinstance(symbols, list)
