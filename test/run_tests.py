"""
Test runner for the realtime alert system.
Runs all unit tests and generates coverage reports.
"""

import unittest
import sys
import os
from pathlib import Path
import argparse
import coverage
import logging

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def setup_test_environment():
    """Setup test environment variables and logging."""
    # Set test environment variables
    os.environ['FIINQUANT_USERNAME'] = 'test_user'
    os.environ['FIINQUANT_PASSWORD'] = 'test_pass'
    os.environ['TELEGRAM_BOT_TOKEN'] = 'test_token'
    os.environ['TELEGRAM_CHAT_ID'] = 'test_chat_id'
    
    # Setup test logging
    logging.basicConfig(
        level=logging.CRITICAL,  # Only show critical errors during tests
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


def discover_tests(test_dir: Path, pattern: str = 'test_*.py'):
    """
    Discover all test files in directory.
    
    Args:
        test_dir: Directory to search for tests
        pattern: File pattern to match
        
    Returns:
        unittest.TestSuite: Test suite containing all discovered tests
    """
    loader = unittest.TestLoader()
    
    # Discover tests
    suite = loader.discover(
        start_dir=str(test_dir),
        pattern=pattern,
        top_level_dir=str(project_root)
    )
    
    return suite


def run_tests_with_coverage(test_suite, coverage_report: bool = True):
    """
    Run tests with coverage reporting.
    
    Args:
        test_suite: Test suite to run
        coverage_report: Whether to generate coverage report
        
    Returns:
        tuple: (success, results)
    """
    # Initialize coverage if requested
    cov = None
    if coverage_report:
        cov = coverage.Coverage()
        cov.start()
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2, buffer=True)
    result = runner.run(test_suite)
    
    # Stop coverage and generate report
    if cov:
        cov.stop()
        cov.save()
        
        print("\n" + "="*50)
        print("COVERAGE REPORT")
        print("="*50)
        
        # Console report
        cov.report()
        
        # HTML report
        html_dir = project_root / 'htmlcov'
        cov.html_report(directory=str(html_dir))
        print(f"\nDetailed HTML coverage report: {html_dir}/index.html")
    
    return result.wasSuccessful(), result


def run_specific_test(test_name: str):
    """
    Run a specific test module or test case.
    
    Args:
        test_name: Name of test module or test case
        
    Returns:
        bool: Success status
    """
    loader = unittest.TestLoader()
    
    try:
        # Try to load as module first
        suite = loader.loadTestsFromName(test_name)
    except Exception as e:
        print(f"Failed to load test '{test_name}': {e}")
        return False
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


def main():
    """Main test runner."""
    parser = argparse.ArgumentParser(description='Run tests for realtime alert system')
    parser.add_argument('--coverage', action='store_true', 
                       help='Generate coverage report')
    parser.add_argument('--test', type=str, 
                       help='Run specific test (module or test case)')
    parser.add_argument('--pattern', type=str, default='test_*.py',
                       help='Test file pattern (default: test_*.py)')
    parser.add_argument('--no-setup', action='store_true',
                       help='Skip test environment setup')
    
    args = parser.parse_args()
    
    # Setup test environment
    if not args.no_setup:
        setup_test_environment()
    
    test_dir = Path(__file__).parent
    
    print("="*60)
    print("REALTIME ALERT SYSTEM - TEST RUNNER")
    print("="*60)
    
    if args.test:
        # Run specific test
        print(f"Running specific test: {args.test}")
        success = run_specific_test(args.test)
        
    else:
        # Run all tests
        print(f"Discovering tests in: {test_dir}")
        print(f"Pattern: {args.pattern}")
        
        test_suite = discover_tests(test_dir, args.pattern)
        test_count = test_suite.countTestCases()
        
        print(f"Found {test_count} test cases")
        print("-" * 60)
        
        if test_count == 0:
            print("No tests found!")
            sys.exit(1)
        
        success, results = run_tests_with_coverage(test_suite, args.coverage)
        
        # Print summary
        print("\n" + "="*60)
        print("TEST SUMMARY")
        print("="*60)
        print(f"Tests run: {results.testsRun}")
        print(f"Failures: {len(results.failures)}")
        print(f"Errors: {len(results.errors)}")
        print(f"Skipped: {len(results.skipped)}")
        print(f"Success: {success}")
        
        # Print failure details
        if results.failures:
            print("\nFAILURES:")
            for test, traceback in results.failures:
                print(f"- {test}: {traceback}")
        
        if results.errors:
            print("\nERRORS:")
            for test, traceback in results.errors:
                print(f"- {test}: {traceback}")
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
