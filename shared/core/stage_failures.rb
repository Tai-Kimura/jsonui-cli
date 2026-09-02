# frozen_string_literal: true

module JsonUI
  # Stages that failed while the build carried on.
  #
  # A build has stages that can fail without the build being wrong to
  # continue: an unreadable colors.json means this run cannot say anything
  # about colours, not that the layouts are broken. Stopping there helps
  # nobody, so those stages log and carry on — and the log then scrolls
  # past, leaving a successful-looking tail that says nothing about it.
  #
  # Measured: a run that could not parse colors.json printed a warning at
  # line 13 of 46 and finished with `Build completed!` and exit 0. A reader
  # who scrolls to the bottom, which is where a reader looks, saw only the
  # success.
  #
  # NOT AN EXIT CODE. The build is not wrong to finish, and turning these
  # into failures would break the window every consuming project builds in.
  # What was missing is that the end of the run says what it could not do.
  #
  # NOTHING IS PRINTED WHEN NOTHING FAILED, so a healthy run's output is
  # byte-identical to before and no downstream baseline moves.
  module StageFailures
    class << self
      def record(stage, message)
        entries << { stage: stage.to_s, message: message.to_s }
      end

      def entries
        @entries ||= []
      end

      def any?
        entries.any?
      end

      def clear!
        @entries = []
      end

      # Called at the end of a build. `logger` is the platform's own.
      #
      # Also appends to the file named by JUI_STAGE_FAILURES when the
      # orchestrating `jui build` set it. Each platform tool is a separate
      # process, so naming the failure at this terminus still leaves it
      # above the orchestrator's own closing block — which is the bottom a
      # reader actually looks at. The file is how it gets there; the
      # variable is set by the caller, so nothing has to guess a path.
      def report!(logger)
        write_ledger
        return if entries.empty?

        logger.error(
          "#{entries.size} stage(s) did not complete; the build carried on " \
          'without them:'
        )
        entries.each do |e|
          logger.error("  - #{e[:stage]}: #{e[:message]}")
        end
      end

      private

      def write_ledger
        path = ENV['JUI_STAGE_FAILURES']
        return if path.nil? || path.empty? || entries.empty?

        require 'json'
        existing = begin
          JSON.parse(File.read(path))
        rescue StandardError
          []
        end
        existing = [] unless existing.is_a?(Array)
        added = entries.map do |e|
          { 'stage' => e[:stage], 'message' => e[:message] }
        end
        merged = existing + added
        File.write(path, JSON.generate(merged))
      rescue StandardError
        nil
      end
    end
  end
end
