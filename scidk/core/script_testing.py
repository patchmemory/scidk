"""
Script test runner for executing validation tests in sandbox.

Coordinates validator and sandbox execution to safely test scripts
against their category contracts.
"""
from typing import TYPE_CHECKING

from .script_sandbox import run_sandboxed
from .script_validators import BaseValidator, ValidationResult, get_validator_for_category

if TYPE_CHECKING:
    from .scripts import Script


class ScriptTestRunner:
    """Runs validation tests on scripts using sandboxed execution."""

    def __init__(self, timeout: int = 10):
        """
        Initialize test runner.

        Args:
            timeout: Default timeout for test execution (seconds)
        """
        self.timeout = timeout

    def run_tests(
        self,
        script: 'Script',
        validator: BaseValidator
    ) -> ValidationResult:
        """
        Run validation tests on a script.

        Executes the script in sandbox and runs category-specific
        contract tests via the provided validator.

        Args:
            script: Script to validate
            validator: Validator instance for script's category

        Returns:
            ValidationResult with pass/fail status and details
        """
        # DEBUG: Log script language and category at validation entry point
        import logging
        logging.getLogger(__name__).warning(f"run_tests: language={script.language!r} category={script.category!r}")

        # Skip sandbox execution for Cypher scripts (they need Neo4j, not Python sandbox)
        if script.language == 'cypher':
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"ScriptTestRunner: Detected Cypher script '{script.id}', skipping sandbox execution")
            # Go directly to validator which has proper Cypher handling
            return validator.validate(script)

        # For Python scripts: First check basic execution in sandbox
        result = run_sandboxed(script.code, timeout=self.timeout)

        if result['returncode'] != 0 and not result['timed_out']:
            # Script has execution errors - return early
            return ValidationResult(
                passed=False,
                errors=[f"Script execution failed: {result['stderr'][:300]}"],
                test_results={'sandbox_execution': False}
            )

        if result['timed_out']:
            # Script timed out
            return ValidationResult(
                passed=False,
                errors=[f"Script execution timed out after {self.timeout}s"],
                test_results={'sandbox_execution': False},
                warnings=['Consider optimizing script performance']
            )

        # Sandbox execution successful - run contract tests
        validation_result = validator.validate(script)

        return validation_result

    def run_tests_for_category(self, script: 'Script') -> ValidationResult:
        """
        Convenience method: automatically select validator for script category.

        Args:
            script: Script to validate

        Returns:
            ValidationResult from appropriate validator
        """
        validator = get_validator_for_category(script.category)
        return self.run_tests(script, validator)
