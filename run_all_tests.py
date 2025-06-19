#!/usr/bin/env python3
"""
Comprehensive Test Runner for Raspberry Ninja Project

This script discovers and runs all test files, generates reports,
shows coverage statistics, and provides recommendations.
"""

import os
import sys
import time
import json
import traceback
import subprocess
import importlib.util
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Tuple
import unittest
from io import StringIO
import re

class TestResult:
    """Container for individual test results"""
    def __init__(self, test_name: str, status: str, duration: float, 
                 error: str = None, output: str = None):
        self.test_name = test_name
        self.status = status  # 'passed', 'failed', 'error', 'skipped'
        self.duration = duration
        self.error = error
        self.output = output

class TestRunner:
    """Main test runner class"""
    
    def __init__(self):
        self.root_dir = Path(__file__).parent
        self.test_results: List[TestResult] = []
        self.coverage_data = {}
        self.start_time = None
        self.end_time = None
        self.pytest_available = self._check_pytest()
        self.coverage_available = self._check_coverage()
        
    def _check_pytest(self) -> bool:
        """Check if pytest is available"""
        try:
            import pytest
            return True
        except ImportError:
            return False
            
    def _check_coverage(self) -> bool:
        """Check if coverage.py is available"""
        try:
            import coverage
            return True
        except ImportError:
            return False
    
    def discover_test_files(self) -> List[Path]:
        """Discover all test files in the project"""
        test_files = []
        
        # Pattern for test files
        test_patterns = ['test_*.py', '*_test.py']
        
        # Directories to exclude
        exclude_dirs = {
            'WSL2-Linux-Kernel', '.git', '__pycache__', 
            'venv', '.venv', 'node_modules', 'build', 'dist'
        }
        
        # Walk through directory tree
        for root, dirs, files in os.walk(self.root_dir):
            # Remove excluded directories
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            
            # Check files against patterns
            for file in files:
                if any(Path(file).match(pattern) for pattern in test_patterns):
                    test_path = Path(root) / file
                    # Skip example and template files
                    if 'example' not in str(test_path).lower():
                        test_files.append(test_path)
        
        # Sort and prioritize validation tests
        test_files = sorted(test_files)
        validation_tests = [f for f in test_files if 'validation' in f.name.lower()]
        other_tests = [f for f in test_files if 'validation' not in f.name.lower()]
        
        return validation_tests + other_tests
    
    def run_test_with_unittest(self, test_file: Path) -> List[TestResult]:
        """Run a test file using unittest"""
        results = []
        
        try:
            # Load the module
            spec = importlib.util.spec_from_file_location(
                test_file.stem, test_file
            )
            module = importlib.util.module_from_spec(spec)
            
            # Capture output
            old_stdout = sys.stdout
            old_stderr = sys.stderr
            stdout_capture = StringIO()
            stderr_capture = StringIO()
            
            try:
                sys.stdout = stdout_capture
                sys.stderr = stderr_capture
                
                # Execute the module
                spec.loader.exec_module(module)
                
                # Find and run test cases
                loader = unittest.TestLoader()
                suite = loader.loadTestsFromModule(module)
                
                # Run tests
                runner = unittest.TextTestRunner(
                    stream=StringIO(), 
                    verbosity=2
                )
                
                start_time = time.time()
                result = runner.run(suite)
                duration = time.time() - start_time
                
                # Process results
                for test, error in result.failures + result.errors:
                    test_name = f"{test_file.stem}.{test._testMethodName}"
                    results.append(TestResult(
                        test_name=test_name,
                        status='failed' if (test, error) in result.failures else 'error',
                        duration=duration / result.testsRun if result.testsRun > 0 else 0,
                        error=error,
                        output=stdout_capture.getvalue()
                    ))
                
                # Add successful tests
                if result.wasSuccessful() and result.testsRun > 0:
                    for test in suite:
                        for test_case in test:
                            test_name = f"{test_file.stem}.{test_case._testMethodName}"
                            if not any(r.test_name == test_name for r in results):
                                results.append(TestResult(
                                    test_name=test_name,
                                    status='passed',
                                    duration=duration / result.testsRun,
                                    output=stdout_capture.getvalue()
                                ))
                
            finally:
                sys.stdout = old_stdout
                sys.stderr = old_stderr
                
        except Exception as e:
            # If module loading fails, try running as script
            results.append(self._run_as_script(test_file))
            
        return results
    
    def _run_as_script(self, test_file: Path) -> TestResult:
        """Run a test file as a script"""
        start_time = time.time()
        
        try:
            result = subprocess.run(
                [sys.executable, str(test_file)],
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            duration = time.time() - start_time
            
            # Determine status from output and return code
            if result.returncode == 0:
                if 'FAILED' in result.stdout or 'ERROR' in result.stdout:
                    status = 'failed'
                else:
                    status = 'passed'
            else:
                status = 'error'
            
            return TestResult(
                test_name=test_file.stem,
                status=status,
                duration=duration,
                error=result.stderr if result.stderr else None,
                output=result.stdout
            )
            
        except subprocess.TimeoutExpired:
            return TestResult(
                test_name=test_file.stem,
                status='error',
                duration=300,
                error="Test timed out after 5 minutes"
            )
        except Exception as e:
            return TestResult(
                test_name=test_file.stem,
                status='error',
                duration=time.time() - start_time,
                error=str(e)
            )
    
    def run_with_pytest(self, test_files: List[Path]) -> List[TestResult]:
        """Run tests using pytest"""
        import pytest
        
        results = []
        
        # Create pytest args
        args = [
            '-v',
            '--tb=short',
            '--json-report',
            '--json-report-file=pytest_report.json'
        ]
        
        # Add coverage if available
        if self.coverage_available:
            args.extend(['--cov=.', '--cov-report=json'])
        
        # Add test files
        args.extend([str(f) for f in test_files])
        
        # Run pytest
        exit_code = pytest.main(args)
        
        # Parse results
        if Path('pytest_report.json').exists():
            with open('pytest_report.json') as f:
                report = json.load(f)
                
            for test in report.get('tests', []):
                results.append(TestResult(
                    test_name=test['nodeid'],
                    status='passed' if test['outcome'] == 'passed' else test['outcome'],
                    duration=test.get('duration', 0),
                    error=test.get('call', {}).get('longrepr') if test['outcome'] != 'passed' else None
                ))
                
            # Clean up
            Path('pytest_report.json').unlink(missing_ok=True)
            
        return results
    
    def analyze_coverage(self) -> Dict[str, Any]:
        """Analyze code coverage if available"""
        coverage_data = {
            'available': False,
            'percentage': 0,
            'files': {},
            'uncovered_lines': []
        }
        
        if self.coverage_available:
            try:
                import coverage
                cov = coverage.Coverage()
                cov.load()
                
                # Get coverage percentage
                coverage_data['percentage'] = cov.report()
                coverage_data['available'] = True
                
                # Get file-level coverage
                for filename in cov.get_data().measured_files():
                    analysis = cov.analysis2(filename)
                    covered = len(analysis[1])
                    missing = len(analysis[3])
                    total = covered + missing
                    
                    if total > 0:
                        coverage_data['files'][filename] = {
                            'covered': covered,
                            'missing': missing,
                            'percentage': (covered / total) * 100
                        }
                        
                        if missing > 0:
                            coverage_data['uncovered_lines'].append({
                                'file': filename,
                                'lines': analysis[3]
                            })
                            
            except Exception as e:
                print(f"Coverage analysis failed: {e}")
                
        return coverage_data
    
    def generate_recommendations(self) -> List[str]:
        """Generate recommendations based on test results"""
        recommendations = []
        
        # Analyze test results
        total_tests = len(self.test_results)
        passed = sum(1 for r in self.test_results if r.status == 'passed')
        failed = sum(1 for r in self.test_results if r.status == 'failed')
        errors = sum(1 for r in self.test_results if r.status == 'error')
        
        # Success rate
        if total_tests > 0:
            success_rate = (passed / total_tests) * 100
            
            if success_rate < 50:
                recommendations.append(
                    "CRITICAL: Less than 50% of tests are passing. "
                    "Immediate attention required for test stability."
                )
            elif success_rate < 80:
                recommendations.append(
                    "WARNING: Test success rate is below 80%. "
                    "Consider prioritizing test fixes."
                )
            elif success_rate < 100:
                recommendations.append(
                    "GOOD: Most tests are passing, but there's room for improvement."
                )
            else:
                recommendations.append(
                    "EXCELLENT: All tests are passing!"
                )
        
        # Specific issues
        if errors > 0:
            recommendations.append(
                f"ERROR: {errors} tests encountered errors. "
                "These may indicate setup issues or missing dependencies."
            )
            
        # Slow tests
        slow_tests = [r for r in self.test_results if r.duration > 10]
        if slow_tests:
            recommendations.append(
                f"PERFORMANCE: {len(slow_tests)} tests took more than 10 seconds. "
                "Consider optimizing or mocking external dependencies."
            )
            
        # Coverage recommendations
        if self.coverage_data.get('available'):
            coverage_pct = self.coverage_data.get('percentage', 0)
            if coverage_pct < 50:
                recommendations.append(
                    "COVERAGE: Code coverage is below 50%. "
                    "Consider adding more unit tests."
                )
            elif coverage_pct < 80:
                recommendations.append(
                    "COVERAGE: Code coverage could be improved. "
                    "Target 80% or higher for better confidence."
                )
                
        # Missing test framework
        if not self.pytest_available:
            recommendations.append(
                "SETUP: Consider installing pytest for better test discovery "
                "and reporting: pip install pytest pytest-json-report"
            )
            
        if not self.coverage_available:
            recommendations.append(
                "SETUP: Consider installing coverage.py for code coverage "
                "analysis: pip install coverage pytest-cov"
            )
            
        # Test organization
        test_files = self.discover_test_files()
        if len(test_files) > 20:
            recommendations.append(
                "ORGANIZATION: Consider organizing tests into subdirectories "
                "by component or feature for better maintainability."
            )
            
        return recommendations
    
    def generate_report(self) -> Dict[str, Any]:
        """Generate comprehensive test report"""
        total_tests = len(self.test_results)
        passed = sum(1 for r in self.test_results if r.status == 'passed')
        failed = sum(1 for r in self.test_results if r.status == 'failed')
        errors = sum(1 for r in self.test_results if r.status == 'error')
        skipped = sum(1 for r in self.test_results if r.status == 'skipped')
        
        report = {
            'summary': {
                'total_tests': total_tests,
                'passed': passed,
                'failed': failed,
                'errors': errors,
                'skipped': skipped,
                'success_rate': (passed / total_tests * 100) if total_tests > 0 else 0,
                'duration': (self.end_time - self.start_time).total_seconds() if self.end_time else 0,
                'timestamp': datetime.now().isoformat(),
                'pytest_available': self.pytest_available,
                'coverage_available': self.coverage_available
            },
            'tests': [],
            'coverage': self.coverage_data,
            'recommendations': self.generate_recommendations(),
            'environment': {
                'python_version': sys.version,
                'platform': sys.platform,
                'cwd': os.getcwd()
            }
        }
        
        # Add detailed test results
        for result in self.test_results:
            test_detail = {
                'name': result.test_name,
                'status': result.status,
                'duration': result.duration
            }
            
            if result.error:
                test_detail['error'] = result.error
                
            if result.output and len(result.output.strip()) > 0:
                test_detail['output'] = result.output[:1000]  # Limit output size
                
            report['tests'].append(test_detail)
            
        # Sort tests by status for easier review
        report['tests'].sort(key=lambda x: (x['status'] != 'failed', x['status'] != 'error', x['name']))
        
        return report
    
    def print_summary(self, report: Dict[str, Any]):
        """Print formatted summary to console"""
        summary = report['summary']
        
        print("\n" + "="*80)
        print(" TEST EXECUTION SUMMARY ")
        print("="*80)
        
        print(f"\nTest Statistics:")
        print(f"  Total Tests: {summary['total_tests']}")
        print(f"  Passed:      {summary['passed']} ({summary['passed']/summary['total_tests']*100:.1f}%)" if summary['total_tests'] > 0 else "  Passed:      0")
        print(f"  Failed:      {summary['failed']}")
        print(f"  Errors:      {summary['errors']}")
        print(f"  Skipped:     {summary['skipped']}")
        print(f"  Duration:    {summary['duration']:.2f} seconds")
        
        # Coverage summary
        if report['coverage']['available']:
            print(f"\nCode Coverage: {report['coverage']['percentage']:.1f}%")
            
        # Failed tests
        failed_tests = [t for t in report['tests'] if t['status'] in ['failed', 'error']]
        if failed_tests:
            print(f"\nFailed Tests ({len(failed_tests)}):")
            for test in failed_tests[:10]:  # Show first 10
                print(f"  - {test['name']} ({test['status']})")
                if 'error' in test and test['error']:
                    error_lines = test['error'].strip().split('\n')
                    for line in error_lines[:3]:  # First 3 lines of error
                        print(f"    {line}")
                        
        # Recommendations
        print("\nRecommendations:")
        for i, rec in enumerate(report['recommendations'], 1):
            print(f"  {i}. {rec}")
            
        print("\n" + "="*80)
        
    def run(self):
        """Main entry point for test runner"""
        print("Raspberry Ninja Test Runner")
        print("="*80)
        
        self.start_time = datetime.now()
        
        # Discover test files
        print("\nDiscovering test files...")
        test_files = self.discover_test_files()
        print(f"Found {len(test_files)} test files")
        
        if not test_files:
            print("No test files found!")
            return
            
        # Run tests
        if self.pytest_available and False:  # Disabled for now, use unittest
            print("\nRunning tests with pytest...")
            self.test_results = self.run_with_pytest(test_files)
        else:
            print("\nRunning tests with unittest...")
            for i, test_file in enumerate(test_files, 1):
                print(f"\n[{i}/{len(test_files)}] Running {test_file.name}...")
                results = self.run_test_with_unittest(test_file)
                if not results:  # Fallback to script execution
                    results = [self._run_as_script(test_file)]
                self.test_results.extend(results)
                
        self.end_time = datetime.now()
        
        # Analyze coverage
        print("\nAnalyzing coverage...")
        self.coverage_data = self.analyze_coverage()
        
        # Generate report
        print("\nGenerating report...")
        report = self.generate_report()
        
        # Save report to file
        report_path = self.root_dir / 'test_report.json'
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)
        print(f"Detailed report saved to: {report_path}")
        
        # Save human-readable report
        readable_report_path = self.root_dir / 'test_report.txt'
        with open(readable_report_path, 'w') as f:
            f.write("RASPBERRY NINJA TEST REPORT\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("="*80 + "\n\n")
            
            f.write("SUMMARY\n")
            f.write("-"*40 + "\n")
            f.write(f"Total Tests: {report['summary']['total_tests']}\n")
            f.write(f"Passed: {report['summary']['passed']}\n")
            f.write(f"Failed: {report['summary']['failed']}\n")
            f.write(f"Errors: {report['summary']['errors']}\n")
            f.write(f"Success Rate: {report['summary']['success_rate']:.1f}%\n")
            f.write(f"Duration: {report['summary']['duration']:.2f} seconds\n\n")
            
            if report['coverage']['available']:
                f.write("COVERAGE\n")
                f.write("-"*40 + "\n")
                f.write(f"Overall Coverage: {report['coverage']['percentage']:.1f}%\n\n")
                
            f.write("RECOMMENDATIONS\n")
            f.write("-"*40 + "\n")
            for rec in report['recommendations']:
                f.write(f"- {rec}\n")
                
            f.write("\n\nFAILED TESTS\n")
            f.write("-"*40 + "\n")
            failed_tests = [t for t in report['tests'] if t['status'] in ['failed', 'error']]
            for test in failed_tests:
                f.write(f"\nTest: {test['name']}\n")
                f.write(f"Status: {test['status']}\n")
                if 'error' in test:
                    f.write(f"Error:\n{test['error']}\n")
                    
        print(f"Human-readable report saved to: {readable_report_path}")
        
        # Print summary to console
        self.print_summary(report)
        
        # Exit with appropriate code
        if report['summary']['failed'] > 0 or report['summary']['errors'] > 0:
            sys.exit(1)
        else:
            sys.exit(0)


if __name__ == "__main__":
    runner = TestRunner()
    runner.run()