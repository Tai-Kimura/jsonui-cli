# frozen_string_literal: true

require_relative "../spec_helper"
require "core/layout_validator"

# A binding where the declaration takes a list and never a string.
#
# `Collection.sections` is declared `type: array` with no `binding`, and
# `"@{secs}"` reached the converters as a String. Each face then calls a list
# method on it — rjui/sjui `each_with_index`, kjui `any?` — so the screen died
# with `NoMethodError: undefined method \x27each\x27 for "@{secs}":String`
# (measured 2026-09-05 on a `jui init` project, web). That is the failure
# furthest from the cause, and which exception you get depends on which
# converter ran first.
#
# The population is derived from `attribute_definitions.json`, never from a
# list of names: the defect IS "the tool assumed something the declaration
# does not say", so a second list would be a second thing to keep in step.
RSpec.describe "a binding on an attribute the declaration gives no binding" do
  def findings(node)
    JsonUIShared::LayoutValidator.validate_layout(node, source_path: "spec.json")
  end

  it "refuses the ticket shape at :error, naming attribute and declaration" do
    w = findings("type" => "Collection", "id" => "c", "sections" => "@{secs}")
    expect(w.size).to eq(1)
    expect(w.first[:level]).to eq(:error)
    expect(w.first[:message]).to include("sections")
    expect(w.first[:message]).to include("type: array")
    expect(JsonUIShared::LayoutValidator.blocking?(w)).to be true
  end

  it "leaves a literal list alone" do
    expect(findings("type" => "Collection", "id" => "c", "sections" => [])).to be_empty
  end

  # The exemption that matters. A binding IS a string, so an attribute that
  # declares `string` legitimately receives one. Firing here would refuse
  # layouts that are correct — `onclick` carries a handler name on every face.
  it "does not fire where the declaration also allows a string" do
    [["View", "onclick", "@{handler}"],
     ["View", "gravity", "@{g}"],
     ["Collection", "insets", "@{i}"],
     ["Collection", "contentInsets", "@{ci}"],
     ["Label", "edgeInset", "@{e}"],
     ["View", "binding_group", "@{bg}"]].each do |type, attr, value|
      expect(findings("type" => type, "id" => "x", attr => value))
        .to be_empty, "#{type}.#{attr} declares string — a binding must not be refused"
    end
  end

  it "does not fire where the declaration allows a binding" do
    [["Collection", "items"], ["Radio", "items"], ["SelectBox", "items"]].each do |type, attr|
      expect(findings("type" => type, "id" => "x", attr => "@{rows}")).to be_empty
    end
  end

  # Positive control for the population: the count comes from the
  # declaration, so a hand-written expectation of WHICH attributes would
  # agree with itself forever. The number is what a reader can re-derive.
  it "covers exactly the attributes declared array-without-binding-or-string" do
    defs = JSON.parse(File.read(File.join(
      File.dirname(JsonUIShared::LayoutValidator.method(:validate_layout).source_location.first),
      "attribute_definitions.json"
    )))
    n = 0
    defs.each do |comp, attrs|
      next unless attrs.is_a?(Hash) && !comp.start_with?("_")
      attrs.each_value do |spec|
        n += 1 if spec.is_a?(Hash) &&
                  JsonUIShared::AttributeValidatorCore.binding_disallowed_by_declaration?(spec)
      end
    end
    expect(n).to eq(43)
  end

  # `Segment.items` keeps its own 1.8.39 arm: that one warns and drops
  # elements rather than refusing the layout, and this rule must not have
  # quietly taken it over.
  it "leaves the Segment.items rule to its own check" do
    w = findings("type" => "Segment", "id" => "s", "items" => "@{opts}")
    expect(w.map { |x| x[:level] }).to eq([:error])
    expect(w.first[:message]).to include("items")
  end
end
