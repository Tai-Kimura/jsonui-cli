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
    expect(n).to eq(44)   # 2.3.22: ScrollView.contentInset (number or array, react)
  end

  # A binding on a closed value — an enum, or number / integer / boolean
  # only — where the declaration gives no binding. Nothing fails there: a
  # face that reads only a literal falls to its default or drops the
  # attribute (measured on TextField.input / maxLength before they declared
  # one: `.keyboardType(.default)`, the attribute gone on web, and
  # `newValue.count > @{n}` written into the Swift). Reported at :warning,
  # so the build carries on.
  describe "a binding on a closed value the declaration gives no binding" do
    it "warns for an enum, a number and a boolean, naming each" do
      w = findings("type" => "View", "id" => "root", "child" => [
        { "type" => "TextField", "id" => "f", "textAlign" => "@{align}", "hintFontSize" => "@{size}" },
        { "type" => "Label", "id" => "l", "fontScaling" => "@{scale}" }
      ])
      expect(w.map { |x| x[:level] }).to eq(%i[warning warning warning])
      expect(w[0][:message]).to include("'textAlign' is a binding (@{align})", "an enum with no binding")
      expect(w[1][:message]).to include("'hintFontSize'", "type: number with no binding")
      expect(w[2][:message]).to include("'fontScaling'", "type: boolean with no binding")
      expect(JsonUIShared::LayoutValidator.blocking?(w)).to be false
    end

    it "is silent once the declaration allows a binding" do
      [["TextField", "input", "@{kb}"], ["TextField", "maxLength", "@{n}"],
       ["TextField", "returnKeyType", "@{rk}"], ["TextField", "autocapitalizationType", "@{cap}"],
       ["TextField", "autocorrectionType", "@{fix}"], ["TextField", "editable", "@{on}"],
       ["TextView", "input", "@{kb}"], ["TextView", "keyboardType", "@{kb}"],
       ["TextView", "maxLength", "@{n}"], ["TextView", "returnKeyType", "@{rk}"],
       ["TextView", "editable", "@{on}"], ["TextField", "secure", "@{hide}"]].each do |type, attr, value|
        expect(findings("type" => type, "id" => "x", attr => value))
          .to be_empty, "#{type}.#{attr} declares binding — it must not be reported"
      end
    end

    it "is silent for a plain string, a literal and template text" do
      expect(findings("type" => "TextField", "id" => "x", "onTextChange" => "@{onEdit}", "hint" => "@{h}")).to be_empty
      expect(findings("type" => "TextField", "id" => "x", "textAlign" => "center", "hintFontSize" => 12)).to be_empty
      expect(findings("type" => "Label", "id" => "x", "fontScaling" => "x @{scale}")).to be_empty
    end

    it "covers exactly the closed values declared without a binding" do
      defs = JSON.parse(File.read(File.join(
        File.dirname(JsonUIShared::LayoutValidator.method(:validate_layout).source_location.first),
        "attribute_definitions.json"
      )))
      enums = 0
      others = 0
      defs.each do |comp, attrs|
        next unless attrs.is_a?(Hash) && !comp.start_with?("_")
        attrs.each_value do |spec|
          next unless spec.is_a?(Hash) &&
                      JsonUIShared::AttributeValidatorCore.binding_ignored_by_declaration?(spec)
          spec["enum"] ? enums += 1 : others += 1
        end
      end
      expect([enums, others]).to eq([55, 142])   # 2.5.61: TextField / TextView keyboard and length attributes moved out
    end
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
