# frozen_string_literal: true

require 'swiftui/section_bounder'

# All fixtures are SYNTHETIC. They replicate the measured anatomy of real
# oversized generated functions (single-child spine -> paren-array containers
# -> form-field stacks) without carrying any consumer content.
RSpec.describe SjuiTools::SwiftUI::SectionBounder do
  let(:bounder) { described_class.new }

  # ---- helpers -------------------------------------------------------------

  def emitted_functions(functions_text)
    lines = functions_text.split("\n")
    starts = lines.each_index.select { |i| lines[i] =~ /private func (\w+)/ }
    starts.map do |s|
      depth = 0
      peak = 0
      body_end = s
      (s...lines.size).each do |i|
        code = described_class.strip_noise(lines[i])
        code.each_char do |ch|
          case ch
          when '{'
            depth += 1
            peak = depth if depth > peak
          when '}'
            depth -= 1
          end
        end
        if i > s && depth <= 0
          body_end = i
          break
        end
      end
      { name: lines[s][/func (\w+)/, 1], depth: peak, lines: body_end - s + 1,
        text: lines[s..body_end].join("\n") }
    end
  end

  # The property the consumer's view_semantic_fingerprint.py checks: splitting
  # may only MOVE content lines between functions and add call scaffolding —
  # the multiset of content lines is invariant.
  def content_lines(text)
    text.split("\n").map(&:strip).reject do |l|
      l.empty? ||
        l.match?(/\A[{}()\[\],]+\z/) ||                       # pure structure
        l.match?(/\A@ViewBuilder private func \w+\(\) -> some View \{\z/) ||
        l.match?(/\A(view: )?AnyView\(\w+\(\)\)[,)]*\z/) ||    # call scaffolding
        l.end_with?('AnyView(')                                # split-open line
    end
  end

  def deep_spine(levels, leaf: 'Text("leaf")')
    openers = [
      'ZStack(alignment: .topLeading) {',
      'Group {',
      'responsive0 {',
      'AdvancedKeyboardAvoidingScrollView(.vertical, showsIndicators: true) {',
    ]
    lines = []
    levels.times do |i|
      lines << ('    ' * i) + (openers[i] || 'VStack(alignment: .leading, spacing: 0) {')
    end
    lines << ('    ' * levels) + leaf
    (levels - 1).downto(0) { |i| lines << ('    ' * i) + '}' }
    lines.join("\n")
  end

  # ---- the hard gate ---------------------------------------------------------

  describe 'depth bounding' do
    it 'bounds a 12-deep single-child spine to MAX_DEPTH per function' do
      _call, functions = bounder.bound(deep_spine(12))
      fns = emitted_functions(functions)
      expect(fns).not_to be_empty
      expect(fns.map { |f| f[:depth] }.max).to be <= described_class::MAX_DEPTH
      expect(bounder.waivers).to be_empty
    end

    it 'bounds mixed multi-child trees without a wrapper-chain explosion' do
      body = <<~SWIFT
        ZStack(alignment: .topLeading) {
            Group {
                responsive0 {
                    VStack(alignment: .leading, spacing: 0) {
                        Text("a")
                        HStack {
                            VStack {
                                Text("b")
                                HStack {
                                    Text("c")
                                        .padding(1)
                                }
                            }
                        }
                        VStack {
                            Text("d")
                        }
                    }
                }
            }
        }
        .background(Color.white)
      SWIFT
      _call, functions = bounder.bound(body)
      fns = emitted_functions(functions)
      expect(fns.map { |f| f[:depth] }.max).to be <= described_class::MAX_DEPTH
      # 9 brace levels packed at ~4 per function: a handful, not one per level.
      expect(fns.size).to be <= 4
    end

    it 'returns the body untouched inside section0 when already within bounds' do
      body = "VStack {\n    Text(\"small\")\n}"
      call, functions = bounder.bound(body)
      expect(call).to eq('AnyView(section0())')
      fns = emitted_functions(functions)
      expect(fns.size).to eq(1)
      expect(fns.first[:text]).to include('Text("small")')
    end
  end

  # ---- boundaries are erased -------------------------------------------------

  describe 'AnyView boundaries' do
    it 'erases every section call site' do
      _call, functions = bounder.bound(deep_spine(12))
      calls = functions.scan(/section0(?:_\d+)+\(\)/)
      expect(calls).not_to be_empty
      calls.each do |call|
        expect(functions).to include("AnyView(#{call})")
      end
    end

    it 'extracts multi-line AnyView slots preserving the slot spelling' do
      body = <<~SWIFT
        VStack {
            WeightedHStack(alignment: .center, spacing: 8, children: [
                (
                  view: AnyView(
                    VStack {
                        Text("left")
                        HStack {
                            VStack {
                                HStack {
                                    Text("deep")
                                }
                            }
                        }
                    }
                    .padding(4)
                  ),
                  weight: 1.0
                ),
                (
                  view: AnyView(
                    VStack {
                        Text("right")
                    }
                  ),
                  weight: 2.0
                )
            ], hasMatchParentCrossAxis: true)
        }
      SWIFT
      _call, functions = bounder.bound(body)
      expect(functions).to match(/view: AnyView\(section0_\d+\(\)\),/)
      expect(functions).to include('], hasMatchParentCrossAxis: true)')
      expect(functions).to include('weight: 1.0')
      expect(functions).to include('weight: 2.0')
      fns = emitted_functions(functions)
      expect(fns.map { |f| f[:depth] }.max).to be <= described_class::MAX_DEPTH
    end
  end

  # ---- scope protection --------------------------------------------------------

  describe 'binding scopes are never cut' do
    it 'keeps a ForEach parameter closure body in one piece' do
      foreach = <<~SWIFT.strip
        ForEach(Array(data.items.enumerated()), id: \\.offset) { cellIndex, cellData in
            HStack {
                Text("cell")
                    .padding(2)
            }
        }
      SWIFT
      body = deep_spine(8, leaf: foreach.split("\n").join("\n" + '    ' * 8))
      _call, functions = bounder.bound(body)
      # The closure body must sit in the SAME function as its ForEach opening.
      fns = emitted_functions(functions)
      holder = fns.find { |f| f[:text].include?('cellIndex, cellData in') }
      expect(holder).not_to be_nil
      expect(holder[:text]).to include('Text("cell")')
    end

    it 'keeps an action closure with its Button' do
      body = <<~SWIFT
        VStack {
            Group {
                VStack {
                    HStack {
                        VStack {
                            HStack {
                                Button(action: {
                                    data.onTap?()
                                }) {
                                    Text("tap")
                                }
                            }
                        }
                    }
                }
            }
        }
      SWIFT
      _call, functions = bounder.bound(body)
      fns = emitted_functions(functions)
      holder = fns.find { |f| f[:text].include?('Button(action: {') }
      expect(holder[:text]).to include('data.onTap?()')
      expect(holder[:text]).to include('Text("tap")')
      expect(fns.map { |f| f[:depth] }.max).to be <= described_class::MAX_DEPTH
    end

    it 'records a waiver instead of silently shipping an uncuttable violation' do
      # Nested control flow (binding frames) all the way down: no safe cut.
      lines = []
      10.times { |i| lines << ('    ' * i) + "if data.flag#{i} {" }
      lines << ('    ' * 10) + 'Text("deep")'
      9.downto(0) { |i| lines << ('    ' * i) + '}' }
      _call, functions = bounder.bound(lines.join("\n"))
      expect(bounder.waivers).not_to be_empty
      expect(functions).to include('Text("deep")') # still emitted
    end
  end

  # ---- typed parameter passing across binding scopes -------------------------

  describe 'scope-crossing cuts with typed parameters' do
    # The exact collection anatomy the converters emit:
    #   let section = ... / if let cellsData = ... { / ForEach(...) { ... in
    def collection_body(cell_inner_depth: 6)
      inner = +''
      cell_inner_depth.times { |i| inner << ('    ' * i) + "VStack {\n" }
      inner << ('    ' * cell_inner_depth) + "Text(\"\\(cellData[\"title\"] ?? \"\")\")\n"
      (cell_inner_depth - 1).downto(0) { |i| inner << ('    ' * i) + "}\n" }
      indented = inner.split("\n").map { |l| ('    ' * 3) + l }.join("\n")
      <<~SWIFT
        VStack {
            let section = data.favorites.sections[0]
            if let cellsData = section.cells?.data {
                ForEach(Array(cellsData.enumerated()), id: \\.offset) { cellIndex, cellData in
        #{indented}
                }
            }
        }
      SWIFT
    end

    it 'cuts below a ForEach closure by passing its params as typed arguments' do
      _call, functions = bounder.bound(collection_body)
      expect(bounder.waivers).to be_empty
      fns = emitted_functions(functions)
      expect(fns.map { |f| f[:depth] }.max).to be <= described_class::MAX_DEPTH
      # Some extracted function takes the closure bindings as parameters...
      expect(functions).to match(/private func section0(?:_\d+)+\((?=.*cellData: \[String: Any\])/)
      # ...and its call site forwards them.
      expect(functions).to match(/AnyView\(section0(?:_\d+)+\(.*cellData: cellData.*\)\)/)
    end

    it 'does not parameterize a name the segment itself binds via if-let' do
      # The listStyle emit cuts at the `if let cellsData = ...` line. The
      # binding lives INSIDE the extracted block — treating it as an outer
      # visible binding produced a call site passing an argument that exists
      # nowhere in the caller ("cannot find 'cellsData' in scope",
      # Collection/listStyle__* / __control/Collection__no-sections).
      inner = +''
      6.times { |i| inner << ('    ' * i) + "VStack {\n" }
      inner << ('    ' * 6) + "Text(\"\\(cellIndex)\")\n"
      5.downto(0) { |i| inner << ('    ' * i) + "}\n" }
      indented = inner.split("\n").map { |l| ('    ' * 4) + l }.join("\n")
      body = <<~SWIFT
        List {
            ForEach(Array(data.items.sections.enumerated()), id: \\.offset) { sectionIndex, section in
                if let cellsData = section.cells?.data, let viewName = section.cells?.viewName {
                    ForEach(Array(cellsData.enumerated()), id: \\.offset) { cellIndex, cellData in
        #{indented}
                    }
                }
            }
        }
        .listStyle(PlainListStyle())
      SWIFT
      call, functions = bounder.bound(body)
      fns = emitted_functions(functions)
      holder = fns.find { |f| f[:text].include?('if let cellsData') }
      next expect(fns).not_to be_empty if holder.nil? # no cut at the if-let line: nothing to leak
      holder_name = holder[:text][/func (\w+)\(/, 1]
      # The holder must not TAKE the name it binds itself...
      expect(holder[:text]).not_to match(/func \w+\([^)]*cellsData:/)
      # ...and its call site (in a sibling function, or `call` when the
      # holder is the root section) must not PASS it.
      call_site = "#{call}\n#{functions}"[/AnyView\(#{holder_name}\([^)]*\)\)/]
      expect(call_site).not_to be_nil
      expect(call_site).not_to include('cellsData')
    end

    it 'detects references made only inside string interpolation' do
      # "\(cellData["title"] ?? "")" is a real reference even though string
      # stripping would hide it — the extracted function must take the param.
      _call, functions = bounder.bound(collection_body)
      holder = emitted_functions(functions).find { |f| f[:text].include?('cellData["title"]') }
      unless holder[:text].include?('cellIndex, cellData in')
        expect(holder[:text]).to match(/func \w+\(.*cellData: \[String: Any\]/)
      end
    end

    it 'refuses to cut when a referenced binding has no known type' do
      # `{ item in` — the table emission never spells the element type.
      inner = +''
      8.times { |i| inner << ('    ' * (i + 1)) + "VStack {\n" }
      inner << ('    ' * 9) + "Text(item.name)\n"
      8.downto(1) { |i| inner << ('    ' * i) + "}\n" }
      body = <<~SWIFT
        List {
            ForEach(rows) { item in
        #{inner.split("\n").map { |l| '        ' + l }.join("\n")}
            }
        }
      SWIFT
      _call, functions = bounder.bound(body)
      # Every function still contains item references only where `item` is
      # bound — nothing was stranded out of scope.
      emitted_functions(functions).each do |f|
        expect(f[:text]).to include('{ item in') if f[:text].include?('item.name')
      end
      expect(bounder.waivers).not_to be_empty
    end

    it 'never cuts a reference to the shadowed map-closure data parameter' do
      body = <<~SWIFT
        VStack {
            let items = cellsData.reconfigured(cellIdProperty: "cellId", autoChangeTrackingId: true).enumerated().map { index, data in
                IdentifiedCellItem(index: index, data: data)
            }
            ForEach(items) { cell in
                Text("row")
            }
        }
      SWIFT
      _call, functions = bounder.bound(body)
      holder = emitted_functions(functions).find { |f| f[:text].include?('IdentifiedCellItem(index: index, data: data)') }
      expect(holder[:text]).to include('{ index, data in')
    end
  end

  # ---- extraction mechanics ------------------------------------------------------

  describe 'modifier chains travel with their view' do
    it 'keeps an extracted container attached to its trailing modifiers' do
      body = deep_spine(9).sub(
        'Text("leaf")',
        "VStack {\n" + ('    ' * 9) + "    Text(\"inner\")\n" + ('    ' * 9) + "}\n" +
        ('    ' * 9) + ".padding(7)\n" + ('    ' * 9) + '.background(Color.blue)'
      )
      _call, functions = bounder.bound(body)
      fns = emitted_functions(functions)
      holder = fns.find { |f| f[:text].include?('Text("inner")') }
      # Whichever function holds the view holds its modifiers.
      expect(holder[:text]).to include('.padding(7)')
      expect(holder[:text]).to include('.background(Color.blue)')
    end
  end

  # ---- the fingerprint property ----------------------------------------------------

  describe 'semantic invariance' do
    it 'moves content lines without adding or dropping any' do
      body = <<~SWIFT
        ZStack(alignment: .topLeading) {
            Group {
                responsive0 {
                    VStack(alignment: .leading, spacing: 0) {
                        Text("f-1")
                            .accessibilityIdentifier("field_one")
                        HStack {
                            VStack {
                                HStack {
                                    Text("f-2")
                                        .fontWeight(.bold)
                                }
                            }
                        }
                        Button(action: {
                            data.onSubmit?()
                        }) {
                            Text("send")
                        }
                        .cornerRadius(4)
                    }
                }
            }
        }
        .background(Color.white)
      SWIFT
      _call, functions = bounder.bound(body)
      expect(content_lines(functions).sort).to eq(content_lines(body).sort)
    end
  end

  # ---- determinism ---------------------------------------------------------------

  describe 'determinism' do
    it 'is a pure function of its input' do
      body = deep_spine(12)
      first = described_class.new.bound(body)
      second = described_class.new.bound(body)
      expect(second).to eq(first)
    end

    it 'names children in document order' do
      body = <<~SWIFT
        VStack {
            VStack {
                Group {
                    VStack {
                        HStack {
                            VStack {
                                Text("first-deep")
                            }
                        }
                    }
                }
            }
            VStack {
                Group {
                    VStack {
                        HStack {
                            VStack {
                                Text("second-deep")
                            }
                        }
                    }
                }
            }
        }
      SWIFT
      _call, functions = bounder.bound(body)
      names = functions.scan(/private func (\w+)\(\)/).flatten
      expect(names.first).to eq('section0')
      expect(names).to eq(names.uniq)
      # Document order: the function containing "first-deep" is named before
      # the one containing "second-deep".
      fns = emitted_functions(functions)
      first_fn = fns.find { |f| f[:text].include?('first-deep') }
      second_fn = fns.find { |f| f[:text].include?('second-deep') }
      expect(fns.index(first_fn)).to be < fns.index(second_fn)
    end
  end

  # ---- metric robustness --------------------------------------------------------

  describe 'measurement' do
    it 'ignores braces and parens inside string literals' do
      body = deep_spine(3, leaf: 'Text("{ ( specimen ) }")')
      _call, functions = bounder.bound(body)
      expect(functions).to include('Text("{ ( specimen ) }")')
      expect(bounder.waivers).to be_empty
    end
  end
end
