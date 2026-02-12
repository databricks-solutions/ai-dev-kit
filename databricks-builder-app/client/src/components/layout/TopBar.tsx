import { Link, useLocation } from 'react-router-dom';
import { useUser } from '@/contexts/UserContext';

interface TopBarProps {
  projectName?: string;
}

export function TopBar({ projectName }: TopBarProps) {
  const location = useLocation();
  const { user } = useUser();

  // Extract username from email for display
  const displayName = user?.split('@')[0] || '';

  return (
    <header className="fixed top-0 left-0 right-0 z-30 h-[var(--header-height)] bg-[var(--color-background)]/70 backdrop-blur-xl backdrop-saturate-150 border-b border-[var(--color-border)]/40 shadow-sm">
      <div className="flex items-center justify-between h-full px-4 lg:px-6">
        {/* Left Section - Logo & Name */}
        <div className="flex items-center gap-4">
          {/* Logo */}
          <Link to="/" className="flex items-center gap-3">
            <div className="w-8 h-8 flex items-center justify-center">
              <svg
                className="w-7 h-7"
                viewBox="33 0 28 31"
                fill="none"
                xmlns="http://www.w3.org/2000/svg"
              >
                <path
                  d="M59.7279 12.5153L47.2039 19.6185L33.8814 12.0502L33.251 12.3884V17.885L47.2039 25.8339L59.7279 18.7306V21.648L47.2039 28.7513L33.8814 21.1829L33.251 21.5212V22.4514L47.2039 30.4002L61.1989 22.4514V16.9548L60.5685 16.6165L47.2039 24.1849L34.7219 17.0816V14.2065L47.2039 21.2675L61.1989 13.3186V7.9066L60.4844 7.52607L47.2039 15.0521L35.3943 8.32941L47.2039 1.64897L56.9541 7.14554L57.8367 6.68044V6.00394L47.2039 0L33.251 7.9066V8.75223L47.2039 16.7011L59.7279 9.59785V12.5153Z"
                  fill="#FF3621"
                />
              </svg>
            </div>
            <h1 className="text-xl font-semibold tracking-tight text-[var(--color-text-heading)]">
              Databricks AI Dev Kit
            </h1>
          </Link>

          {/* Project Name Breadcrumb */}
          {projectName && (
            <>
              <span className="text-[var(--color-text-muted)]">/</span>
              <span className="text-[var(--color-text-primary)] font-medium truncate max-w-[200px]">
                {projectName}
              </span>
            </>
          )}
        </div>

        {/* Right Section - Navigation & User */}
        <div className="flex items-center gap-6">
          {/* Navigation */}
          <nav className="flex items-center gap-1">
            <Link
              to="/"
              className={`
                relative px-4 py-2 text-sm font-medium transition-colors duration-300
                ${
                  location.pathname === '/'
                    ? 'text-[var(--color-foreground)]'
                    : 'text-[var(--color-muted-foreground)] hover:text-[var(--color-foreground)]'
                }
              `}
            >
              <span className="relative z-10">Projects</span>
              {location.pathname === '/' && (
                <span className="absolute bottom-1.5 left-4 right-4 h-0.5 bg-[var(--color-accent-primary)] rounded-full" />
              )}
            </Link>
            <Link
              to="/doc"
              className={`
                relative px-4 py-2 text-sm font-medium transition-colors duration-300
                ${
                  location.pathname === '/doc'
                    ? 'text-[var(--color-foreground)]'
                    : 'text-[var(--color-muted-foreground)] hover:text-[var(--color-foreground)]'
                }
              `}
            >
              <span className="relative z-10">Docs</span>
              {location.pathname === '/doc' && (
                <span className="absolute bottom-1.5 left-4 right-4 h-0.5 bg-[var(--color-accent-primary)] rounded-full" />
              )}
            </Link>
          </nav>

          {/* User Email */}
          {displayName && (
            <div
              className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-[var(--color-bg-secondary)] border border-[var(--color-border)] shadow-sm"
              title={user || undefined}
            >
              <div className="w-6 h-6 rounded-full bg-[var(--color-accent-primary)] flex items-center justify-center text-white text-xs font-medium">
                {displayName.charAt(0).toUpperCase()}
              </div>
              <span className="text-sm text-[var(--color-text-primary)] max-w-[120px] truncate">
                {displayName}
              </span>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
