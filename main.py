"""
Main entry point for Real-time Alert System.
Provides command-line interface to run different components.
"""

import sys
import asyncio
import argparse
import logging
from pathlib import Path
from datetime import datetime
import multiprocessing as mp
import subprocess
import os
from dotenv import load_dotenv

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Load environment variables from .env file
load_dotenv()

from utils.helpers import load_config, get_env_variable, setup_logging
from jobs.realtime_monitor import RealtimeMonitor
from jobs.main_orchestrator import MainOrchestrator
from jobs.telegram_bot import TradingTelegramBot
from utils.logger import initialize_global_logger


def check_environment():
    """Check if environment is properly configured."""
    required_vars = [
        'FIINQUANT_USERNAME',
        'FIINQUANT_PASSWORD', 
        'TELEGRAM_BOT_TOKEN',
        'TELEGRAM_CHAT_ID'
    ]
    
    missing_vars = []
    for var in required_vars:
        if not get_env_variable(var):
            missing_vars.append(var)
    
    if missing_vars:
        print("❌ Missing required environment variables:")
        for var in missing_vars:
            print(f"   - {var}")
        print("\nPlease check your .env file or environment configuration.")
        return False
    
    return True


def run_realtime_monitor(args):
    """Run the realtime monitor."""
    print("🚀 Starting Real-time Monitor with FiinQuant...")
    
    if not check_environment():
        return 1
    
    try:
        # Create and run monitor
        monitor = RealtimeMonitor(config_path=args.config)
        
        asyncio.run(monitor.start())
        
    except KeyboardInterrupt:
        print("\n📴 Shutting down Real-time Monitor...")
        return 0
    except Exception as e:
        logging.error(f"Monitor failed: {str(e)}")
        return 1


def run_streamlit_dashboard(args):
    """Run Streamlit dashboard."""
    print("📊 Starting Streamlit Dashboard...")
    
    try:
        # Get configuration
        port = get_env_variable('STREAMLIT_PORT', 8501)
        host = get_env_variable('STREAMLIT_HOST', 'localhost')
        
        # Run streamlit command
        streamlit_cmd = [
            sys.executable, '-m', 'streamlit', 'run',
            'jobs/streamlit_app.py',
            '--server.port', str(port),
            '--server.address', str(host),
            '--theme.base', 'dark'
        ]
        
        if args.config != 'config/config.yaml':
            streamlit_cmd.extend(['--', '--config', args.config])
        
        # Change to project directory
        os.chdir(project_root)
        
        # Run command
        subprocess.run(streamlit_cmd, check=True)
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Streamlit failed: {e}")
        return 1
    except KeyboardInterrupt:
        print("\n📴 Shutting down Streamlit Dashboard...")
        return 0


def run_telegram_bot(args):
    """Run Telegram bot standalone."""
    print("🤖 Starting Telegram Bot...")
    
    if not check_environment():
        return 1
    
    try:
        config = load_config(args.config)
        bot = TradingTelegramBot(config)
        
        asyncio.run(bot.start_bot())
        
        # Keep running
        while True:
            asyncio.sleep(1)
            
    except KeyboardInterrupt:
        print("\n📴 Shutting down Telegram Bot...")
        return 0
    except Exception as e:
        logging.error(f"Telegram bot failed: {str(e)}")
        return 1


def run_tests(args):
    """Run test suite."""
    print("🧪 Running Tests...")
    
    try:
        test_cmd = [
            sys.executable, 
            str(project_root / 'test' / 'run_tests.py')
        ]
        
        if args.coverage:
            test_cmd.append('--coverage')
        
        if hasattr(args, 'test_pattern'):
            test_cmd.extend(['--pattern', args.test_pattern])
        
        # Run tests
        result = subprocess.run(test_cmd, cwd=project_root)
        return result.returncode
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Tests failed: {e}")
        return 1


def run_main_orchestrator(args):
    """Run the main orchestrator (recommended)."""
    print("🚀 Starting Main Orchestrator (Full System)...")
    
    if not check_environment():
        return 1
    
    try:
        # Create and run orchestrator
        orchestrator = MainOrchestrator(config_path=args.config)
        
        asyncio.run(orchestrator.start())
        
    except KeyboardInterrupt:
        print("\n📴 Shutting down Main Orchestrator...")
        return 0
    except Exception as e:
        logging.error(f"Main Orchestrator failed: {str(e)}")
        return 1


def run_all_services(args):
    """Run all services simultaneously."""
    print("🚀 Starting All Services...")
    
    if not check_environment():
        return 1
    
    processes = []
    
    try:
        # Start real-time monitor
        monitor_process = mp.Process(
            target=run_realtime_monitor,
            args=(args,),
            name="RealtimeMonitor"
        )
        monitor_process.start()
        processes.append(monitor_process)
        
        # Start Streamlit dashboard  
        dashboard_process = mp.Process(
            target=run_streamlit_dashboard,
            args=(args,),
            name="StreamlitDashboard"
        )
        dashboard_process.start()
        processes.append(dashboard_process)
        
        print("✅ All services started successfully!")
        print("\n📊 Dashboard: http://localhost:8501")
        print("🤖 Telegram bot: Check your Telegram chat")
        print("📈 Monitor: Check logs for trading signals")
        print("\nPress Ctrl+C to stop all services...")
        
        # Wait for processes
        for process in processes:
            process.join()
            
    except KeyboardInterrupt:
        print("\n📴 Shutting down all services...")
        
        # Terminate all processes
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=10)
                
                if process.is_alive():
                    process.kill()
        
        return 0


def setup_project():
    """Setup project directories and files."""
    print("⚙️  Setting up project...")
    
    # Create directories
    directories = [
        'log',
        'database', 
        'log/signals',
        'log/replay',
        'log/audit'
    ]
    
    for directory in directories:
        Path(project_root / directory).mkdir(parents=True, exist_ok=True)
    
    # Create .env file if it doesn't exist
    env_file = project_root / '.env'
    if not env_file.exists():
        example_file = project_root / 'env_example.txt'
        if example_file.exists():
            env_file.write_text(example_file.read_text())
            print(f"✅ Created .env file from template")
            print("⚠️  Please edit .env with your credentials")
        else:
            print("⚠️  No .env template found, please create manually")
    
    # Create database directory
    db_dir = project_root / 'database'
    db_dir.mkdir(exist_ok=True)
    
    print("✅ Project setup completed")
    return 0


def main():
    """Main entry point with argument parsing."""
    parser = argparse.ArgumentParser(
        description='Real-time Trading Alert System',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py orchestrator         # Run main orchestrator (recommended)
  python main.py monitor              # Run realtime monitor only
  python main.py dashboard            # Run Streamlit dashboard  
  python main.py bot                  # Run Telegram bot
  python main.py all                  # Run all services separately
  python main.py test --coverage      # Run tests with coverage
  python main.py setup                # Setup project
        """
    )
    
    # Global arguments
    parser.add_argument('--config', default='config/config.yaml',
                       help='Configuration file path')
    parser.add_argument('--log-level', default='INFO',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                       help='Log level')
    
    # Subcommands
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Main orchestrator command (recommended)
    orchestrator_parser = subparsers.add_parser('orchestrator', help='Run main orchestrator (recommended - includes all features)')
    
    # Monitor command
    monitor_parser = subparsers.add_parser('monitor', help='Run realtime monitor only')
    
    # Dashboard command
    dashboard_parser = subparsers.add_parser('dashboard', help='Run Streamlit dashboard')
    
    # Bot command
    bot_parser = subparsers.add_parser('bot', help='Run Telegram bot')
    
    # All services command
    all_parser = subparsers.add_parser('all', help='Run all services separately')
    
    # Test command
    test_parser = subparsers.add_parser('test', help='Run tests')
    test_parser.add_argument('--coverage', action='store_true',
                            help='Generate coverage report')
    test_parser.add_argument('--pattern', default='test_*.py',
                            help='Test file pattern')
    
    # Setup command
    setup_parser = subparsers.add_parser('setup', help='Setup project')
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Show banner
    print("="*60)
    print("🚀 REAL-TIME TRADING ALERT SYSTEM")
    print("="*60)
    print(f"📅 Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"⚙️  Config: {args.config}")
    print(f"📡 Data Source: FiinQuant Realtime")
    print("="*60)
    
    # Route to appropriate handler
    if args.command == 'orchestrator':
        return run_main_orchestrator(args)
    elif args.command == 'monitor':
        return run_realtime_monitor(args)
    elif args.command == 'dashboard':
        return run_streamlit_dashboard(args)
    elif args.command == 'bot':
        return run_telegram_bot(args)
    elif args.command == 'all':
        return run_all_services(args)
    elif args.command == 'test':
        return run_tests(args)
    elif args.command == 'setup':
        return setup_project()
    else:
        parser.print_help()
        print("\n💡 Quick start:")
        print("   python main.py setup        # First time setup")
        print("   python main.py orchestrator # Run full system (recommended)")
        print("   python main.py all          # Run services separately")
        return 1


if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)
