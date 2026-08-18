# frozen_string_literal: true

module RjuiTools
  module Core
    # Framework adapters own every web-framework-specific string the codegen
    # emits: router imports, router types, the link component wiring, and the
    # RSC directive. Emitters stay framework-neutral and ask the adapter
    # resolved from `web_framework` in rjui.config.json.
    #
    # `web_framework` accepts either:
    #   - a built-in name string (default: "next"), or
    #   - an object declaring a custom adapter, so any React-family framework
    #     (Remix, TanStack Start, ...) can be targeted from config alone:
    #
    #       "web_framework": {
    #         "name": "remix",
    #         "use_client_directive": "",
    #         "link_import_line": "import { Link } from '@remix-run/react';",
    #         "link_href_attribute": "to",
    #         "router_hook_import": "import { useNavigate } from '@remix-run/react';",
    #         "router_hook_statement": "const router = useNavigate();",
    #         "router_type_import": "import { NavigateFunction } from 'react-router-dom';",
    #         "router_type": "NavigateFunction",
    #         "router_type_jsdoc": "import('react-router-dom').NavigateFunction"
    #       }
    #
    # Every key is optional; omitted keys fall back to the neutral defaults
    # documented on CustomAdapter (empty imports are suppressed line-and-all,
    # never emitted as blank lines).
    module Frameworks
      CONFIG_KEY = 'web_framework'
      DEFAULT_FRAMEWORK = 'next'

      # Line-level emit helpers shared by all adapters. They exist so that a
      # custom adapter declaring an empty string suppresses the whole line
      # instead of leaving a blank one behind.
      module EmitHelpers
        def use_client_prefix
          use_client_directive.empty? ? '' : "#{use_client_directive}\n\n"
        end

        def router_type_import_prefix
          router_type_import.empty? ? '' : "#{router_type_import}\n"
        end

        def router_hook_import_prefix
          router_hook_import.empty? ? '' : "#{router_hook_import}\n"
        end

        def router_hook_statement_line(indent = '  ')
          router_hook_statement.empty? ? '' : "#{indent}#{router_hook_statement}\n"
        end
      end

      # Next.js App Router. The reference adapter: its output is the
      # historical emit, byte for byte.
      class NextAdapter
        include EmitHelpers

        def name
          'next'
        end

        def use_client_directive
          '"use client";'
        end

        def link_import_line
          "import Link from 'next/link';"
        end

        def link_href_attribute
          'href'
        end

        def router_hook_import
          'import { useRouter } from "next/navigation";'
        end

        def router_hook_statement
          'const router = useRouter();'
        end

        def router_type_import
          'import { AppRouterInstance } from "next/dist/shared/lib/app-router-context.shared-runtime";'
        end

        def router_type
          'AppRouterInstance'
        end

        def router_type_jsdoc
          'import("next/dist/shared/lib/app-router-context.shared-runtime").AppRouterInstance'
        end
      end

      # Adapter declared inline in rjui.config.json. Defaults are neutral:
      # no RSC directive, plain <Link href>, untyped router, no extra imports.
      class CustomAdapter
        include EmitHelpers

        STRING_KEYS = %w[
          use_client_directive
          link_import_line
          link_href_attribute
          router_hook_import
          router_hook_statement
          router_type_import
          router_type
          router_type_jsdoc
        ].freeze
        ALLOWED_KEYS = (STRING_KEYS + %w[name]).freeze

        DEFAULTS = {
          'use_client_directive' => '',
          'link_import_line' => '',
          'link_href_attribute' => 'href',
          'router_hook_import' => '',
          'router_hook_statement' => '',
          'router_type_import' => '',
          'router_type' => 'any',
          'router_type_jsdoc' => nil # falls back to router_type
        }.freeze

        attr_reader :name

        def initialize(spec)
          unknown = spec.keys - ALLOWED_KEYS
          unless unknown.empty?
            raise ArgumentError,
                  "Unknown web_framework key(s) #{unknown.join(', ')} (allowed: #{ALLOWED_KEYS.join(', ')})"
          end

          bad = spec.reject { |_k, v| v.is_a?(String) }.keys
          unless bad.empty?
            raise ArgumentError, "web_framework key(s) #{bad.join(', ')} must be strings"
          end

          @name = spec['name'] || 'custom'
          @values = DEFAULTS.merge(spec.slice(*STRING_KEYS))
          @values['router_type_jsdoc'] ||= @values['router_type']
        end

        STRING_KEYS.each do |key|
          define_method(key) { @values[key] }
        end
      end

      REGISTRY = {
        'next' => NextAdapter.new
      }.freeze

      # Rewrites the RSC directive in template files copied verbatim into the
      # consumer tree (NetworkImage, useColorMode, ...). Templates are
      # authored in the Next dialect; for adapters that declare no directive
      # the line (and its trailing blank) is dropped, and a different
      # non-empty directive replaces it in place. Next output is unchanged,
      # byte for byte.
      def self.apply_directive(content, adapter)
        directive_re = /^"use client";\n(\n)?/
        if adapter.use_client_directive == '"use client";'
          content
        elsif adapter.use_client_directive.empty?
          content.sub(directive_re, '')
        else
          content.sub(directive_re) { "#{adapter.use_client_directive}\n#{Regexp.last_match(1)}" }
        end
      end

      def self.for(config)
        raw = config && config[CONFIG_KEY]
        case raw
        when nil
          REGISTRY.fetch(DEFAULT_FRAMEWORK)
        when String
          REGISTRY.fetch(raw) do
            raise ArgumentError,
                  "Unknown web_framework '#{raw}' in rjui.config.json " \
                  "(built-in: #{REGISTRY.keys.join(', ')}; or declare a custom adapter object)"
          end
        when Hash
          CustomAdapter.new(raw)
        else
          raise ArgumentError,
                "web_framework must be a built-in name string or a custom adapter object (got #{raw.class})"
        end
      end
    end
  end
end
