import React from 'react';

export const Logo: React.FC<{ className?: string }> = ({ className }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    {/* Abstract Brain/Circuit Shape */}
    <path d="M9.5 2C9.5 2 9.5 4 12 4C14.5 4 14.5 2 14.5 2" />
    <path d="M12 4V10" />
    <path d="M12 10C12 10 8 10 8 15C8 20 12 22 12 22C12 22 16 20 16 15C16 10 12 10 12 10Z" />
    <path d="M8 15C5 15 3 13 3 10C3 7 6 7 6 7" />
    <path d="M16 15C19 15 21 13 21 10C21 7 18 7 18 7" />
    <path d="M12 12V16" />
    
    {/* Central Node */}
    <circle cx="12" cy="15" r="1.5" fill="currentColor" stroke="none" />
    
    {/* Connection points */}
    <circle cx="12" cy="2" r="1" fill="currentColor" stroke="none" opacity="0.5" />
    <circle cx="3" cy="7" r="1" fill="currentColor" stroke="none" opacity="0.5" />
    <circle cx="21" cy="7" r="1" fill="currentColor" stroke="none" opacity="0.5" />
  </svg>
);