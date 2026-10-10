export default function Logo({ size = 26, showText = false, className = '' }) {
  return (
    <div className={`logo-wrapper ${className}`} style={{ display: 'inline-flex', alignItems: 'center', gap: '10px' }}>
      <svg
        width={size}
        height={size}
        viewBox="0 0 36 36"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        style={{ flexShrink: 0 }}
      >
        <defs>
          <linearGradient id="agentos-gradient" x1="4" y1="4" x2="32" y2="32" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#ffffff" />
            <stop offset="50%" stopColor="#10b981" />
            <stop offset="100%" stopColor="#06b6d4" />
          </linearGradient>
          <linearGradient id="agentos-accent" x1="6" y1="6" x2="30" y2="30" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#10b981" />
            <stop offset="100%" stopColor="#3b82f6" />
          </linearGradient>
          <filter id="logo-soft-glow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="1.5" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>
        </defs>

        {/* Ambient background aura */}
        <circle cx="18" cy="18" r="16" fill="rgba(16, 185, 129, 0.06)" />

        {/* Outer Minimalist Smooth Squircle */}
        <rect
          x="3.5"
          y="3.5"
          width="29"
          height="29"
          rx="10"
          fill="rgba(255, 255, 255, 0.03)"
          stroke="rgba(255, 255, 255, 0.12)"
          strokeWidth="1.2"
        />

        {/* Dynamic Tri-Node Neural Swarm (Minimalist A-O Coordination) */}
        {/* Central Core Loop */}
        <circle
          cx="18"
          cy="18"
          r="5.5"
          stroke="url(#agentos-gradient)"
          strokeWidth="2"
          strokeLinecap="round"
        />

        {/* 3 Coordinated Agent Nodes at 120° offsets */}
        <circle cx="18" cy="9" r="2.2" fill="#ffffff" filter="url(#logo-soft-glow)" />
        <circle cx="10" cy="23.5" r="2.2" fill="#10b981" />
        <circle cx="26" cy="23.5" r="2.2" fill="#06b6d4" />

        {/* Orbit bridges connecting agents to core */}
        <path
          d="M18 11.2 V12.5 M11.8 22.4 L13 21.5 M24.2 22.4 L23 21.5"
          stroke="rgba(255, 255, 255, 0.35)"
          strokeWidth="1.4"
          strokeLinecap="round"
        />
      </svg>
      {showText && (
        <span style={{ fontWeight: 600, fontSize: '1.05rem', letterSpacing: '-0.02em', color: 'var(--text-primary)' }}>
          AgentOS
        </span>
      )}
    </div>
  );
}
