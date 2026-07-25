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

    @pytest.mark.skipif(
        not TREE_SITTER_AVAILABLE, reason="inheritance detection requires tree-sitter"
    )
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


@pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="tree-sitter not available")
class TestRubyEnrichment:
    """v0.4.1 parity features: mixins, visibility, bare calls, constants."""

    def _analyze(self, source):
        return RubyAnalyzer("test.rb", source).analyze()

    def test_mixins_collected_on_class(self):
        symbols = self._analyze(
            "class Foo\n  include Comparable\n  include Enumerable, Sortable\n"
            "  prepend Auditable\nend\n"
        )
        foo = next(s for s in symbols if s.name == "Foo")
        assert foo.mixins == ["Comparable", "Enumerable", "Sortable", "Auditable"]

    def test_extend_self_and_dynamic_args_skipped(self):
        symbols = self._analyze("module Bar\n  extend self\n  include make_mod()\nend\n")
        bar = next(s for s in symbols if s.name == "Bar")
        assert bar.mixins is None

    def test_scope_resolution_mixin(self):
        symbols = self._analyze("class Job\n  include Sidekiq::Job\nend\n")
        job = next(s for s in symbols if s.name == "Job")
        assert job.mixins == ["Sidekiq::Job"]

    def test_visibility_modifiers(self):
        symbols = self._analyze(
            "class Foo\n  def pub; end\n\n  private\n\n  def hidden; end\n\n"
            "  protected\n\n  def guarded; end\n\n  public\n\n  def open_again; end\nend\n"
        )
        by_name = {s.name: s for s in symbols}
        assert by_name["pub"].visibility is None
        assert by_name["hidden"].visibility == "private"
        assert by_name["guarded"].visibility == "protected"
        assert by_name["open_again"].visibility is None

    def test_bare_calls_in_dependencies(self):
        symbols = self._analyze(
            "class Foo\n  def run\n    reset\n    helper()\n    MAX = 1 if false\n  end\nend\n"
        )
        run = next(s for s in symbols if s.name == "run")
        assert "reset" in run.dependencies
        assert "helper" in run.dependencies

    def test_bare_call_skips_keywords_and_constants(self):
        symbols = self._analyze(
            "class Foo\n  def run\n    self\n    nil\n    Logger\n    private\n  end\nend\n"
        )
        run = next(s for s in symbols if s.name == "run")
        for skipped in ("self", "nil", "Logger", "private"):
            assert skipped not in run.dependencies

    def test_constant_assignment_extracted(self):
        symbols = self._analyze('MAX_SIZE = 100\n\nclass Foo\n  VERSION = "1.0"\nend\n')
        consts = {s.name: s for s in symbols if s.type == "constant"}
        assert "MAX_SIZE" in consts
        assert consts["MAX_SIZE"].parent is None
        assert consts["VERSION"].parent == "Foo"

    def test_local_assignment_not_extracted(self):
        symbols = self._analyze("x = 1\n")
        assert [s for s in symbols if s.type == "constant"] == []

    def test_nested_class_gains_module_parent(self):
        symbols = self._analyze("module Outer\n  class Inner\n  end\nend\n")
        inner = next(s for s in symbols if s.name == "Inner")
        assert inner.parent == "Outer"


@pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="tree-sitter not available")
class TestRailsMetaprogramming:
    """Rails class-body macros generate invocable methods a static parser must see."""

    def _analyze(self, source):
        return RubyAnalyzer("model.rb", source).analyze()

    def test_associations(self):
        symbols = self._analyze(
            "class User < ApplicationRecord\n"
            "  belongs_to :account\n"
            "  has_many :posts, dependent: :destroy\n"
            "  has_one :profile\n"
            "  has_and_belongs_to_many :roles\n"
            "end\n"
        )
        by_name = {s.name: s for s in symbols}
        for assoc in ("account", "posts", "profile", "roles"):
            assert assoc in by_name, assoc
            assert by_name[assoc].parent == "User"
            assert by_name[assoc].modifiers[0].startswith("association:")

    def test_attr_accessors_each_name(self):
        symbols = self._analyze(
            "class User\n  attr_accessor :token, :count\n  attr_reader :id\nend\n"
        )
        names = {s.name for s in symbols if s.modifiers == ["attr"]}
        assert names == {"token", "count", "id"}

    def test_scopes(self):
        symbols = self._analyze(
            "class User < Base\n"
            "  scope :active, -> { where(active: true) }\n"
            "  scope :recent, ->(n) { limit(n) }\n"
            "end\n"
        )
        scopes = {s.name for s in symbols if s.modifiers == ["scope"]}
        assert scopes == {"active", "recent"}

    def test_delegate_with_and_without_prefix(self):
        symbols = self._analyze(
            "class User\n"
            "  delegate :name, :email, to: :profile, prefix: true\n"
            "  delegate :city, to: :address\n"
            "end\n"
        )
        delegated = {s.name for s in symbols if s.modifiers == ["delegated"]}
        assert delegated == {"profile_name", "profile_email", "city"}

    def test_define_method_symbol_literal(self):
        symbols = self._analyze("class C\n  define_method(:dynamic) { 1 }\nend\n")
        assert any(s.name == "dynamic" and s.modifiers == ["dynamic"] for s in symbols)

    def test_validates_is_not_a_symbol(self):
        # validates declares behavior but no invocable method named after the field.
        symbols = self._analyze("class C\n  validates :email, presence: true\nend\n")
        assert not any(s.name == "email" for s in symbols)

    def test_macros_do_not_break_dsl_wrapped_classes(self):
        symbols = self._analyze(
            "namespace :admin do\n  class Dashboard\n    def show; end\n  end\nend\n"
        )
        assert any(s.type == "class" and s.name == "Dashboard" for s in symbols)
        assert any(s.name == "show" for s in symbols)

    def test_macros_coexist_with_mixins_and_requires(self):
        analyzer = RubyAnalyzer(
            "m.rb",
            'require "json"\nclass Foo\n  include Comparable\n  belongs_to :bar\nend\n',
        )
        symbols = analyzer.analyze()
        assert analyzer.imports == ["json"]
        foo = next(s for s in symbols if s.name == "Foo")
        assert foo.mixins == ["Comparable"]
        assert any(s.name == "bar" for s in symbols)
