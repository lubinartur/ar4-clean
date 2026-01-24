import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useAir4 } from '../contexts/Air4Context';
import { MemoryItem, Fact } from '../types';
import {
  Search,
  RefreshCw,
  Zap,
  Database,
  Filter,
  Hash,
  Trash2,
  User,
  MapPin,
  Globe,
  Utensils,
  Target,
  Layers,
  Pin,
  Info,
  ChevronDown,
  Copy,
  ClipboardCheck,
  CheckSquare,
  Square,
  Archive,
  Calendar,
  X,
  MoreVertical,
  Check,
} from 'lucide-react';

interface ProfileData {
  subject: string;
  profile?: string[];
}

// Helper для парсинга meta-префикса
function splitMeta(content: string) {
  const text = content ?? "";
  const m = text.match(/^\s*\[Meta:\s*([^\]]+)\]\s*/i);
  if (!m) return { meta: null as string | null, clean: text.trim() };
  const meta = m[1].trim();
  const clean = text.slice(m[0].length).trim();
  return { meta, clean };
}

// Helper для парсинга meta-строки
function parseMeta(meta: string) {
  const obj: Record<string, string> = {};
  meta.split(",").forEach(part => {
    const idx = part.indexOf(":");
    if (idx === -1) return;
    const key = part.slice(0, idx).trim();
    const value = part.slice(idx + 1).trim();
    if (key && value) obj[key] = value;
  });
  return obj;
}

interface MemoryProps {
  activeSessionId: string | null;
}

const Memory: React.FC<MemoryProps> = ({ activeSessionId }) => {
  const air4 = useAir4();
  // B1: Unified state for read-only memory items
  const [items, setItems] = useState<MemoryItem[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [offset, setOffset] = useState(0);
  const [searchTerm, setSearchTerm] = useState('');
  const [debouncedSearchTerm, setDebouncedSearchTerm] = useState('');
  const [activeTab, setActiveTab] = useState<'all' | 'notes' | 'facts' | 'sessions' | 'docs' | 'profile' | 'pinned'>('all');
  const [loading, setLoading] = useState(false);
  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [facts, setFacts] = useState<Fact[]>([]);
  const [showNoisyPinned, setShowNoisyPinned] = useState(false);
  const [metaOpen, setMetaOpen] = useState<Record<string, boolean>>({});
  const [queryOpen, setQueryOpen] = useState<Record<string, boolean>>({});
  const [copiedSessionId, setCopiedSessionId] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState<Record<string, boolean>>({});
  const [profileCategoriesOpen, setProfileCategoriesOpen] = useState<Record<string, boolean>>({
    profile: true,
  });
  // C3.1: Promote panel state
  const [promotePanelOpen, setPromotePanelOpen] = useState<Record<string, boolean>>({});
  const [promoteLoading, setPromoteLoading] = useState<Record<string, boolean>>({});
  const [promoteSuccess, setPromoteSuccess] = useState<Record<string, boolean>>({});
  
  // B3.1: Memory hygiene state
  const [hideDuplicates, setHideDuplicates] = useState(false);
  const [ageFilter, setAgeFilter] = useState<string>('all'); // 'all' | '7d' | '30d' | '90d'
  const [showArchived, setShowArchived] = useState(false);  // C3.0: Show archived items toggle
  const [selectMode, setSelectMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [archivingProgress, setArchivingProgress] = useState<{ current: number; total: number } | null>(null);
  
  // Archive safety: confirm + undo (client-only)
  const [showConfirmArchive, setShowConfirmArchive] = useState<{ id: string; item: MemoryItem } | null>(null);
  const [pendingArchive, setPendingArchive] = useState<{ id: string; item: MemoryItem; timerId: NodeJS.Timeout; expiresAt: number } | null>(null);
  const [undoCountdown, setUndoCountdown] = useState<number>(0);
  
  // B2.5: Inline capture state
  const [captureText, setCaptureText] = useState('');
  const [loadingCapture, setLoadingCapture] = useState(false);
  const [captureStatus, setCaptureStatus] = useState<string | null>(null);
  const captureTextareaRef = useRef<HTMLTextAreaElement | null>(null);
  
  // B1: AbortController for cancelling in-flight requests
  const abortControllerRef = useRef<AbortController | null>(null);
  // HOTFIX: prevent request storm - track in-flight requests
  const inFlightRef = useRef(false);
  // HOTFIX: prevent request storm - track current offset in ref to avoid deps
  const offsetRef = useRef(0);
  // C2.3: Guard to apply nav params only once
  const navParamsAppliedRef = useRef(false);
  
  // B2.5: Check if item would be visible in current tab
  const wouldItemBeVisibleInCurrentTab = useCallback((item: MemoryItem, tab: string): boolean => {
    if (tab === 'all') return true;
    if (tab === 'notes') {
      // Notes tab: backend already filters by type=note, so items with type=note are visible
      const itemType = (item as any)?.type || (item.meta as any)?.type || (item.meta as any)?.kind || '';
      return itemType.toLowerCase() === 'note';
    }
    if (tab === 'pinned') {
      const metaTag = (item.meta as any)?.tag;
      const contentHasRagPin = item.content.includes('[Meta:') && item.content.includes('Tag: rag_pin');
      return metaTag === 'rag_pin' || contentHasRagPin;
    }
    if (tab === 'docs') {
      const src = (item as any).source || '';
      return item.namespace === 'docs' || src !== '';
    }
    // For other tabs, check namespace match
    return item.namespace === tab;
  }, []);
  
  const toggleMeta = (id: string) => setMetaOpen(p => ({...p, [id]: !p[id]}));
  const toggleQuery = (id: string) => setQueryOpen(p => ({...p, [id]: !p[id]}));
  
  const handleCopySession = (sessionId: string, memoryId: string) => {
    navigator.clipboard.writeText(sessionId);
    setCopiedSessionId(memoryId);
    setTimeout(() => setCopiedSessionId(null), 2000);
  };
  
  // Helper functions для определения мусорных воспоминаний
  const SMALLTALK_RE = /(привет|здаров|как дела|спасибо|ок(ей)?|норм|понял|ага|давай|хорошо|ясно)/i;
  
  function isQuestionLike(text: string) {
    const t = text.trim();
    return t.includes("?") || /^(что|как|почему|зачем|где|когда|сколько|какой|какая|какие|можно ли)\b/i.test(t);
  }
  
  function isTooShort(text: string) {
    return text.trim().length < 22;
  }
  
  function isNoisyMemory(text: string) {
    const t = (text ?? "").trim();
    if (!t) return true;
    if (SMALLTALK_RE.test(t)) return true;
    if (isTooShort(t)) return true;
    if (isQuestionLike(t)) return true;
    return false;
  }

  // B2.2: Map UI tab to Memory Bank type
  // HOTFIX: omit type for ALL - return undefined for 'all' to avoid sending type=all to backend
  function tabToBankType(activeTab: string): string | undefined {
    const mapping: Record<string, string | undefined> = {
      'all': undefined,  // HOTFIX: omit type for ALL - backend expects no type param for all items
      'notes': 'note',  // Backend expects 'note', not 'notes'
      'chat': 'chat',
      'captures': 'captures',
      'facts': undefined,  // Facts handled separately
      'profile': undefined, // Profile handled separately
      'summaries': 'summaries',
      'patterns': 'patterns',
      'pinned': undefined,  // Pinned uses tag filter
      'docs': undefined     // Docs uses namespace filter
    };
    return mapping[activeTab];
  }

  // B2.2: Unified loadBankPage function
  // HOTFIX: prevent request storm - stable callback with minimal deps
  // HOTFIX: prevent initial empty + loading stuck
  const loadBankPage = useCallback(async ({ reset }: { reset: boolean }) => {
    if (!activeSessionId) return;
    
    // HOTFIX: prevent request storm - prevent overlapping fetches
    // Check BEFORE setLoading to avoid stuck loading state
    if (inFlightRef.current) {
      return; // Don't change loading state if request is already in flight
    }
    
    // Abort previous request
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    
    const ac = new AbortController();
    abortControllerRef.current = ac;
    
    // HOTFIX: prevent request storm - mark as in-flight BEFORE setLoading
    inFlightRef.current = true;
    
    const sessionId = activeSessionId;
    const bankType = tabToBankType(activeTab);
    const currentOffset = reset ? 0 : offsetRef.current;
    
    // HOTFIX: prevent initial empty + loading stuck - set loading AFTER inFlightRef check
    setLoading(true);
    
    try {
      const result = await air4.getMemoryBank({
        sessionId: sessionId,
        type: bankType,
        tag: activeTab === 'pinned' ? 'rag_pin' : undefined,
        limit: 50,
        offset: currentOffset,
        includeArchived: showArchived,  // C3.0: Pass showArchived flag to backend
      });
      
      if (!ac.signal.aborted) {
        if (reset) {
          setItems(result.items);
          const newOffset = result.items.length;
          setOffset(newOffset);
          offsetRef.current = newOffset;
        } else {
          // Append without duplicates
          setItems(prev => {
            const existingIds = new Set(prev.map(item => item.id));
            const newItems = result.items.filter(item => !existingIds.has(item.id));
            return [...prev, ...newItems];
          });
          setOffset(prev => {
            const newOffset = prev + result.items.length;
            offsetRef.current = newOffset;
            return newOffset;
          });
        }
        setHasMore(result.has_more);
      }
    } catch (e: any) {
      // Don't log AbortError as real error, but let finally run to clear loading
      if (e?.name !== 'AbortError') {
        console.error('[Memory] Failed to load bank page:', e);
      }
    } finally {
      // Always clear loading state, even if request was aborted
      setLoading(false);
      // HOTFIX: prevent request storm - clear in-flight flag
      inFlightRef.current = false;
    }
  }, [activeSessionId, activeTab, air4, showArchived]);  // C3.0: Reload when showArchived changes

  // B1: Load more function for pagination
  const loadMore = useCallback(async () => {
    if (loading || !hasMore || !activeSessionId) return;
    await loadBankPage({ reset: false });
  }, [loading, hasMore, activeSessionId, loadBankPage]);

  // C2.3: Read navigation params from localStorage on mount and apply once
  useEffect(() => {
    if (navParamsAppliedRef.current) return; // Already applied
    
    try {
      const navParamsStr = localStorage.getItem('air4_memory_nav_params');
      if (navParamsStr) {
        const navParams = JSON.parse(navParamsStr);
        // C2.3: Apply tab and search params (session_id is handled by App.tsx via event)
        if (navParams.tab && ['all', 'notes', 'facts', 'sessions', 'docs', 'profile', 'pinned'].includes(navParams.tab)) {
          setActiveTab(navParams.tab as 'all' | 'notes' | 'facts' | 'sessions' | 'docs' | 'profile' | 'pinned');
        }
        if (navParams.q && typeof navParams.q === 'string') {
          setSearchTerm(navParams.q);
        }
        // C2.3: Mark as applied and clear params
        navParamsAppliedRef.current = true;
        localStorage.removeItem('air4_memory_nav_params');
      }
    } catch (e) {
      console.debug('[C2.3] Failed to read nav params:', e);
      // Clear invalid params
      localStorage.removeItem('air4_memory_nav_params');
    }
  }, [air4]); // Only run once on mount

  // B1: Debounce search term (300ms)
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearchTerm(searchTerm);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchTerm]);

  // B2.3: Normalize search term (trim, collapse whitespace)
  const normalize = useCallback((term: string): string => {
    return term.trim().replace(/\s+/g, ' ').toLowerCase();
  }, []);

  // B3.1: Normalize text for dedupe key (trim + collapse whitespace + lowercase)
  const normalizeText = useCallback((text: string): string => {
    return (text || '').trim().replace(/\s+/g, ' ').toLowerCase();
  }, []);

  // B3.1: Generate dedupe key for an item
  const getDedupeKey = useCallback((item: MemoryItem): string => {
    const type = (item.meta as any)?.type || item.category || '';
    const tag = (item.meta as any)?.tag || '';
    const text = normalizeText(item.text || item.content || '');
    return `${type}|${tag}|${text}`;
  }, [normalizeText]);

  // B3.1: Get item age in days
  const getItemAgeDays = useCallback((item: MemoryItem): number => {
    const created_at = (item.meta as any)?.created_at || item.timestamp;
    if (!created_at) return 0;
    const createdDate = typeof created_at === 'number' 
      ? new Date(created_at * 1000) 
      : new Date(created_at);
    const now = new Date();
    const diffMs = now.getTime() - createdDate.getTime();
    return Math.floor(diffMs / (1000 * 60 * 60 * 24));
  }, []);

  // HOTFIX: badge should follow item.type (not namespace)
  // Enhanced: getEffectiveKind includes namespace fallback for chat items stored as type=note
  const getEffectiveKind = useCallback((item: MemoryItem): string => {
    // Priority: item.type -> meta.kind -> meta.type -> namespace (especially for chat) -> fallback
    const t = (item as any)?.type;
    if (t != null && t !== '') return t;

    const k = (item?.meta as any)?.kind;
    if (k != null && k !== '') return k;

    const mt = (item?.meta as any)?.type;
    if (mt != null && mt !== '') return mt;

    // IMPORTANT: namespace fallback - especially for chat messages stored as type=note
    const ns = item.namespace;
    if (ns === "chat") return "chat";
    if (ns != null && ns !== '') return ns;

    return "item";
  }, []);

  // HOTFIX: badge should follow item.type (not namespace)
  const getBadgeLabel = useCallback((item: MemoryItem): string => {
    const kindRaw = getEffectiveKind(item).toLowerCase();

    if (kindRaw === "note" || kindRaw === "notes") return "NOTES";
    if (kindRaw === "chat") return "CHAT";
    return kindRaw.toUpperCase();
  }, [getEffectiveKind]);

  const normalizedSearch = useMemo(() => normalize(debouncedSearchTerm), [debouncedSearchTerm, normalize]);
  const isFiltering = normalizedSearch.length >= 2;

  // B2.3: Render highlighted text (safe, no regex DoS)
  const renderHighlighted = useCallback((text: string, searchTerm: string): React.ReactNode => {
    if (!isFiltering || !searchTerm) return text;
    
    // B2.3: Use normalized search for finding matches (case-insensitive)
    const lowerText = text.toLowerCase();
    const lowerSearch = searchTerm.toLowerCase();
    const parts: React.ReactNode[] = [];
    let lastIndex = 0;
    let index = lowerText.indexOf(lowerSearch, lastIndex);
    
    while (index !== -1) {
      // Add text before match
      if (index > lastIndex) {
        parts.push(text.substring(lastIndex, index));
      }
      // Add highlighted match (use original text to preserve case)
      parts.push(
        <span key={index} className="bg-amber-200/30 rounded px-1">
          {text.substring(index, index + searchTerm.length)}
        </span>
      );
      lastIndex = index + searchTerm.length;
      index = lowerText.indexOf(lowerSearch, lastIndex);
    }
    
    // Add remaining text
    if (lastIndex < text.length) {
      parts.push(text.substring(lastIndex));
    }
    
    return parts.length > 0 ? <>{parts}</> : text;
  }, [isFiltering]);

  // B1: Single unified useEffect for loading items
  useEffect(() => {
    // B1.1: Guard - NO request if activeSessionId is missing
    if (!activeSessionId) {
      setItems([]);
      setHasMore(false);
      setOffset(0);
      offsetRef.current = 0; // HOTFIX: sync ref
      setLoading(false);
      // Clear any in-flight request
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }
      inFlightRef.current = false; // HOTFIX: clear in-flight flag
      return;
    }
    
    // Reset offset when query, tab, session, or showArchived changes
    setOffset(0);
    offsetRef.current = 0; // HOTFIX: sync ref immediately
    
    // HOTFIX: prevent initial empty + loading stuck - clear in-flight flag on reset
    inFlightRef.current = false;
    
    // Abort previous request
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    
    const ac = new AbortController();
    abortControllerRef.current = ac;
    
    // activeSessionId is guaranteed to exist at this point
    const sessionId = activeSessionId;
    
    // Special handling for profile and facts tabs (keep existing behavior)
    if (activeTab === 'profile') {
      setLoading(true);
      air4.getFactsProfile('Arch').then(p => {
        if (!ac.signal.aborted) {
          setProfile(p);
        }
      }).catch(e => {
        // Don't log AbortError as real error
        if (e?.name !== 'AbortError') {
          console.error('[Store/Profile] Failed to load profile:', e);
        }
      }).finally(() => {
        // Always clear loading state, even if request was aborted
        setLoading(false);
      });
      return;
    }
    
    if (activeTab === 'facts') {
      setLoading(true);
      air4.getFacts('Arch', 200).then(f => {
        if (!ac.signal.aborted) {
          setFacts(f);
        }
      }).catch(e => {
        // Don't log AbortError as real error
        if (e?.name !== 'AbortError') {
          console.error('[Store/Facts] Failed to load facts:', e);
        }
      }).finally(() => {
        // Always clear loading state, even if request was aborted
        setLoading(false);
      });
      return;
    }
    
    // B2.2: Use loadBankPage for unified loading
    loadBankPage({ reset: true });
    
    return () => {
      ac.abort();
    };
  }, [activeTab, activeSessionId, loadBankPage, showArchived]);  // C3.0: Reload when showArchived changes

  // HOTFIX: prevent request storm - sync offsetRef with offset state
  useEffect(() => {
    offsetRef.current = offset;
  }, [offset]);

  // Очистка metaOpen и queryOpen при смене activeTab
  useEffect(() => {
    setMetaOpen({});
    setQueryOpen({});
    setMenuOpen({}); // HOTFIX: Close menus when switching tabs
    // B3.1: Clear selection when switching tabs
    setSelectedIds(new Set());
  }, [activeTab]);

  // P2.3.3: Clear selection when showArchived toggles to avoid invisible selections
  useEffect(() => {
    setSelectedIds(new Set());
    if (selectMode) {
      setSelectMode(false);
    }
  }, [showArchived]);

  // HOTFIX: Close dropdown menus when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (!target.closest('.menu-dropdown-container')) {
        setMenuOpen({});
      }
    };
    document.addEventListener('click', handleClickOutside);
    return () => document.removeEventListener('click', handleClickOutside);
  }, []);

  // B3.1: Load hygiene preferences from localStorage on mount
  useEffect(() => {
    try {
      const stored = localStorage.getItem('air4_memory_hygiene_v1');
      if (stored) {
        const prefs = JSON.parse(stored);
        if (prefs.hideDuplicates !== undefined) setHideDuplicates(prefs.hideDuplicates);
        if (prefs.ageFilter) setAgeFilter(prefs.ageFilter);
        if (prefs.selectMode !== undefined) setSelectMode(prefs.selectMode);
      }
    } catch (e) {
      console.warn('[Memory] Failed to load hygiene preferences:', e);
    }
  }, []);

  // B3.1: Save hygiene preferences to localStorage on change
  useEffect(() => {
    try {
      localStorage.setItem('air4_memory_hygiene_v1', JSON.stringify({
        hideDuplicates,
        ageFilter,
        selectMode,
      }));
    } catch (e) {
      console.warn('[Memory] Failed to save hygiene preferences:', e);
    }
  }, [hideDuplicates, ageFilter, selectMode]);

  // B2.6: Listen for memory-saved events from Chat.tsx and refresh list
  useEffect(() => {
    const handleMemorySaved = (event: Event) => {
      const customEvent = event as CustomEvent<{ sessionId: string }>;
      const savedSessionId = customEvent.detail?.sessionId;
      
      // Only refresh if event sessionId matches activeSessionId (or if we're on all/session-agnostic view)
      if (!activeSessionId || !savedSessionId || savedSessionId !== activeSessionId) {
        return; // Ignore events for other sessions
      }
      
      // Reset and reload: abort current request, reset state, trigger reload via offset reset
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      setOffset(0);
      setItems([]);
      // Reload will be triggered by the main useEffect dependency on offset/activeSessionId
    };
    
    window.addEventListener("air4:memory-saved", handleMemorySaved);
    return () => {
      window.removeEventListener("air4:memory-saved", handleMemorySaved);
    };
  }, [activeSessionId]); // Only re-subscribe when activeSessionId changes

  // B2.2: Memory Bank actions (Promote / Archive / Delete)
  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!activeSessionId) return;
    
    // Optimistic UI update: remove item immediately
    const prevItems = [...items];
    setItems(items.filter(item => item.id !== id));
    
    try {
      const success = await air4.deleteMemoryItem(id, activeSessionId);
      if (!success) {
        // Rollback on error
        setItems(prevItems);
        console.error('[Memory] Delete failed for item', id);
      }
    } catch (error) {
      // Rollback on error
      setItems(prevItems);
      console.error('[Memory] Delete error:', error);
    }
  };

  const handleArchive = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!activeSessionId) return;
    
    const item = items.find(i => i.id === id);
    if (!item) return;
    
    // Show confirm modal
    setShowConfirmArchive({ id, item });
  };

  // Confirm archive: start delayed archive with undo
  const confirmArchive = useCallback(() => {
    if (!showConfirmArchive || !activeSessionId) return;
    
    const { id, item } = showConfirmArchive;
    setShowConfirmArchive(null);
    
    // Store item for potential restore
    const itemToRestore = item;
    
    // C3.0: Optimistic UI update - if showArchived is ON, keep item but mark as archived; if OFF, remove it
    if (showArchived) {
      // Keep item but mark as archived
      setItems(prev => prev.map(i => {
        if (i.id === id) {
          const updatedMeta = { ...(i.meta || {}), archived: true, archived_at: Math.floor(Date.now() / 1000) };
          return { ...i, meta: updatedMeta };
        }
        return i;
      }));
    } else {
      // Remove item from list
      setItems(prev => prev.filter(i => i.id !== id));
    }
    
    // Create 5-second timer
    const expiresAt = Date.now() + 5000;
    let countdown = 5;
    setUndoCountdown(countdown);
    
    const timerId = setInterval(() => {
      countdown -= 1;
      setUndoCountdown(countdown);
      
      if (countdown <= 0) {
        clearInterval(timerId);
        // Timer expired: call backend
        air4.archiveMemoryItem(id, activeSessionId).then(success => {
          if (!success) {
            // C3.0: Rollback on error: restore item
            if (showArchived) {
              setItems(prev => prev.map(i => {
                if (i.id === id) {
                  return itemToRestore; // Restore original item
                }
                return i;
              }));
            } else {
              setItems(prev => [itemToRestore, ...prev]);
            }
            console.error('[Memory] Archive failed for item', id);
          }
          setPendingArchive(null);
          setUndoCountdown(0);
        }).catch(error => {
          // C3.0: Rollback on error: restore item
          if (showArchived) {
            setItems(prev => prev.map(i => {
              if (i.id === id) {
                return itemToRestore; // Restore original item
              }
              return i;
            }));
          } else {
            setItems(prev => [itemToRestore, ...prev]);
          }
          console.error('[Memory] Archive error:', error);
          setPendingArchive(null);
          setUndoCountdown(0);
        });
      }
    }, 1000);
    
    setPendingArchive({ id, item, timerId, expiresAt });
  }, [showConfirmArchive, activeSessionId, air4, showArchived]);

  // Undo archive: cancel timer and restore item
  const undoArchive = useCallback(() => {
    if (!pendingArchive) return;
    
    clearInterval(pendingArchive.timerId);
    
    // C3.0: Restore item - if showArchived is ON, update item; if OFF, add it back
    if (showArchived) {
      setItems(prev => prev.map(i => {
        if (i.id === pendingArchive.item.id) {
          return pendingArchive.item; // Restore original item
        }
        return i;
      }));
    } else {
      // Restore item to top of list
      setItems(prev => [pendingArchive.item, ...prev]);
    }
    
    setPendingArchive(null);
    setUndoCountdown(0);
  }, [pendingArchive, showArchived]);

  // C3.0: Unarchive handler with optimistic UI update
  const handleUnarchive = useCallback(async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!activeSessionId) return;
    
    const item = items.find(i => i.id === id);
    if (!item) return;
    
    // Optimistic UI update: mark item as unarchived immediately
    setItems(prev => prev.map(i => {
      if (i.id === id) {
        const updatedMeta = { ...(i.meta || {}), archived: false };
        if ('archived_at' in updatedMeta) {
          delete updatedMeta.archived_at;
        }
        return { ...i, meta: updatedMeta };
      }
      return i;
    }));
    
    try {
      const success = await air4.unarchiveMemoryItem(id, activeSessionId);
      if (!success) {
        // Rollback on error
        setItems(prev => prev.map(i => {
          if (i.id === id) {
            return item; // Restore original item
          }
          return i;
        }));
        console.error('[C3.0] Unarchive failed for item', id);
      } else {
        console.debug('[C3.0] Unarchived item', id);
        // If current tab filter would hide it, remove it; else keep it
        // (Filtering is handled by useMemo, so item will be shown/hidden automatically)
      }
    } catch (error) {
      // Rollback on error
      setItems(prev => prev.map(i => {
        if (i.id === id) {
          return item; // Restore original item
        }
        return i;
      }));
      console.error('[C3.0] Unarchive error:', error);
    }
  }, [activeSessionId, air4, items]);

  // C3.1: Promote item with optimistic UI update and tab visibility respect
  const promoteItem = useCallback(async (id: string, targetType: "chat" | "note" | "fact", targetTag?: string) => {
    if (!activeSessionId) return;
    
    const item = items.find(i => i.id === id);
    if (!item) return;
    
    console.debug(`[C3.1] Promoting item ${id} to ${targetType}${targetTag ? ` with tag ${targetTag}` : ''}`);
    
    // Set loading state
    setPromoteLoading(prev => ({ ...prev, [id]: true }));
    
    // Optimistic UI update: update item type/tag in local state
    const prevItems = [...items];
    const updatedItem = {
      ...item,
      type: targetType,
      category: targetType as any,
      meta: {
        ...(item.meta || {}),
        kind: targetType,
        type: targetType,
        ...(targetTag ? { tag: targetTag } : {}),
        updated_at: Math.floor(Date.now() / 1000)
      }
    };
    
    setItems(items.map(i => {
      if (i.id === id) {
        return updatedItem;
      }
      return i;
    }));
    
    try {
      const success = await air4.promoteMemoryItem(id, targetType, targetTag, activeSessionId);
      if (!success) {
        // Rollback on error
        setItems(prevItems);
        setPromoteLoading(prev => {
          const next = { ...prev };
          delete next[id];
          return next;
        });
        console.error('[C3.1] Promote failed for item', id);
        return;
      }
      
      // C3.1: Check if item should be visible in current tab after promotion
      const shouldBeVisible = wouldItemBeVisibleInCurrentTab(updatedItem, activeTab);
      if (!shouldBeVisible) {
        // Remove item from list if it's not visible in current tab
        setItems(prev => prev.filter(i => i.id !== id));
        console.debug(`[C3.1] Item ${id} not visible in tab ${activeTab}, removing from list`);
      } else {
        console.debug(`[C3.1] Item ${id} visible in tab ${activeTab}, keeping in list`);
      }
      
      // Show success feedback
      setPromoteSuccess(prev => ({ ...prev, [id]: true }));
      setTimeout(() => {
        setPromoteSuccess(prev => {
          const next = { ...prev };
          delete next[id];
          return next;
        });
      }, 1000);
      
      // Close promote panel
      setPromotePanelOpen(prev => {
        const next = { ...prev };
        delete next[id];
        return next;
      });
      
      console.debug(`[C3.1] Successfully promoted item ${id} to ${targetType}`);
    } catch (e) {
      // Rollback on error
      setItems(prevItems);
      console.error("[C3.1] Promote failed", e);
    } finally {
      setPromoteLoading(prev => {
        const next = { ...prev };
        delete next[id];
        return next;
      });
    }
  }, [activeSessionId, air4, items, activeTab, wouldItemBeVisibleInCurrentTab]);

  const handlePromote = async (id: string, target_type: string, target_tag?: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    if (!activeSessionId) return;
    
    // Optimistic UI update: update item type/tag in local state
    const prevItems = [...items];
    setItems(items.map(item => {
      if (item.id === id) {
        const updatedMeta = { ...item.meta, kind: target_type, type: target_type };
        if (target_tag) {
          updatedMeta.tag = target_tag;
        }
        return {
          ...item,
          category: target_type,
          meta: updatedMeta
        };
      }
      return item;
    }));
    
    try {
      const success = await air4.promoteMemoryItem(id, target_type, target_tag, activeSessionId);
      if (!success) {
        // Rollback on error
        setItems(prevItems);
        console.error('[Memory] Promote failed for item', id);
      } else {
        // If promoted item no longer matches current filter, remove it
        // B2.x: align promote filter with backend type=note
        const tabToType: Record<string, string | undefined> = {
          'all': undefined,
          'notes': 'note',  // Backend expects 'note', not 'notes'
          'chat': 'chat',
          'facts': 'facts',
          'summaries': 'summaries',
          'captures': 'captures',
          'patterns': 'patterns',
        };
        const expectedType = tabToType[activeTab];
        if (expectedType && target_type !== expectedType) {
          setItems(items.filter(item => item.id !== id));
        }
      }
    } catch (error) {
      // Rollback on error
      setItems(prevItems);
      console.error('[Memory] Promote error:', error);
    }
  };

  const handleBulkDelete = async () => {
    // B2.2: Bulk delete not implemented yet (keep no-op)
  };

  // B2.5: Save captured note
  const MIN_CAPTURE_LEN = 5;  // C3.2: Backend requires min 5 chars
  const handleCaptureSave = useCallback(async () => {
    const text = (captureText || "").trim();  // C3.2: Derive trimmed text once
    
    // C3.2: Validate minimum length before network call
    if (text.length < MIN_CAPTURE_LEN) {
      setCaptureStatus('Min 5 characters');
      setTimeout(() => setCaptureStatus(null), 1500);
      return;
    }
    
    if (loadingCapture || !activeSessionId) return;

    setLoadingCapture(true);
    const textToSave = text;  // C3.2: Use pre-trimmed text

    try {
      const success = await air4.addMemoryNote(activeSessionId, textToSave, "manual");
      if (!success) {
        console.error('[Memory] Failed to save captured note');
        setLoadingCapture(false);
        return;
      }

      // Optimistic insert: create MemoryItem-like object
      const now = Date.now();
      const nowSeconds = Math.floor(now / 1000);
      const newItem: MemoryItem = {
        id: `tmp-${now}-${Math.random().toString(36).substring(2, 9)}`,
        text: textToSave,
        content: textToSave,
        type: 'note',
        category: 'note',
        namespace: 'notes',
        timestamp: now,
        source: 'note',
        meta: {
          created_at: nowSeconds,
          tag: 'manual',
          kind: 'note',
          type: 'note',
          namespace: 'notes',
          session_id: activeSessionId,
          source: 'note',
          user_id: 'dev'
        }
      };

      // Only insert if it would be visible in current tab
      if (wouldItemBeVisibleInCurrentTab(newItem, activeTab)) {
        setItems(prev => [newItem, ...prev]);
      }

      // Clear input and show status
      setCaptureText('');
      setCaptureStatus('Saved');
      setTimeout(() => setCaptureStatus(null), 1500);
      // Keep focus on textarea
      if (captureTextareaRef.current) {
        captureTextareaRef.current.focus();
        captureTextareaRef.current.style.height = 'auto';
      }
    } catch (error) {
      console.error('[Memory] Error saving captured note:', error);
    } finally {
      setLoadingCapture(false);
    }
  }, [captureText, loadingCapture, activeSessionId, activeTab, air4, wouldItemBeVisibleInCurrentTab]);

  // B3.1: Bulk archive selected items (sequential, no request storms)
  const archiveSelected = useCallback(async () => {
    if (!activeSessionId || selectedIds.size === 0) return;
    
    // Show confirm modal for bulk archive
    const ok = window.confirm(`Archive ${selectedIds.size} items?`);
    if (!ok) return;
    
    const idsArray = Array.from(selectedIds);
    setArchivingProgress({ current: 0, total: idsArray.length });
    
    for (let i = 0; i < idsArray.length; i++) {
      const id = idsArray[i];
      setArchivingProgress({ current: i + 1, total: idsArray.length });
      
      try {
        const success = await air4.archiveMemoryItem(id, activeSessionId);
        if (success) {
          // Optimistic UI update: remove item immediately
          setItems(prev => prev.filter(item => item.id !== id));
          setSelectedIds(prev => {
            const next = new Set(prev);
            next.delete(id);
            return next;
          });
        } else {
          console.error('[Memory] Archive failed for item', id);
        }
      } catch (error) {
        console.error('[Memory] Archive error for item', id, error);
        // Continue with next item
      }
    }
    
    setArchivingProgress(null);
  }, [activeSessionId, selectedIds, air4]);

  // Cleanup timer on unmount or when pendingArchive changes
  useEffect(() => {
    return () => {
      if (pendingArchive) {
        clearInterval(pendingArchive.timerId);
      }
    };
  }, [pendingArchive]);

  // B1: Use items directly (filtering is done in backend via typeFilter)
  // B2.3: Add client-side search filtering with useMemo
  // B3.1: Add dedupe + aging filters before search
  // C3.0: Helper to check if item is archived
  const isItemArchived = useCallback((item: MemoryItem): boolean => {
    return (item.meta as any)?.archived === true;
  }, []);

  const { filteredMemories, duplicateCounts } = useMemo(() => {
    let filtered = items.filter((m) => {
      // C3.0: Filter archived items based on showArchived toggle
      const isArchived = isItemArchived(m);
      if (!showArchived && isArchived) {
        return false; // Hide archived items when showArchived is OFF
      }
      
      if (activeTab === 'all') return true;

      if (activeTab === 'pinned') {
        // Pinned: проверяем tag в metadata или в тексте
        const metaTag = (m.meta as any)?.tag;
        const contentHasRagPin = m.content.includes('[Meta:') && m.content.includes('Tag: rag_pin');
        const isPinned = metaTag === 'rag_pin' || contentHasRagPin;
        
        if (!isPinned) return false;
        
        // Если showNoisyPinned === false, фильтруем мусор
        if (!showNoisyPinned) {
          // Извлекаем чистый текст (убираем метаданные префикс)
          let cleanText = m.content;
          if (cleanText.includes('[Meta:')) {
            const metaEnd = cleanText.indexOf(']\n\n');
            if (metaEnd !== -1) {
              cleanText = cleanText.substring(metaEnd + 4);
            }
          }
          return !isNoisyMemory(cleanText);
        }
        
        return true;
      }

      if (activeTab === 'notes') {
        // Notes: backend already filters by type=note, so all items from backend are notes
        // No additional client-side filtering needed
        return true;
      }

      if (activeTab === 'docs') {
        // Документы: либо явный namespace 'docs', либо любые записи с непустым source
        const src = (m as any).source || '';
        return m.namespace === 'docs' || src !== '';
      }

      return m.namespace === activeTab;
    });

    // B3.1: Apply aging filter (before dedupe to reduce work)
    if (ageFilter !== 'all') {
      const daysThreshold = ageFilter === '7d' ? 7 : ageFilter === '30d' ? 30 : 90;
      filtered = filtered.filter((m) => {
        const ageDays = getItemAgeDays(m);
        return ageDays >= daysThreshold;
      });
    }

    // B3.1: Apply dedupe filter (keep newest per dedupeKey)
    const duplicateCountsMap = new Map<string, number>();
    if (hideDuplicates) {
      const dedupeMap = new Map<string, MemoryItem>();
      
      // First pass: collect all items by dedupeKey and count duplicates
      filtered.forEach((m) => {
        const key = getDedupeKey(m);
        const existing = dedupeMap.get(key);
        duplicateCountsMap.set(key, (duplicateCountsMap.get(key) || 0) + 1);
        
        if (!existing) {
          dedupeMap.set(key, m);
        } else {
          // Keep newest: compare by created_at (DESC), fallback to id (DESC)
          const existingCreated = (existing.meta as any)?.created_at || existing.timestamp || 0;
          const currentCreated = (m.meta as any)?.created_at || m.timestamp || 0;
          
          if (currentCreated > existingCreated) {
            dedupeMap.set(key, m);
          } else if (currentCreated === existingCreated && m.id > existing.id) {
            dedupeMap.set(key, m);
          }
        }
      });
      
      // Second pass: keep only items in dedupeMap
      filtered = filtered.filter((m) => {
        const key = getDedupeKey(m);
        const kept = dedupeMap.get(key);
        return kept && kept.id === m.id;
      });
    }

    // B2.3: Apply client-side search filter (only if searchTerm length >= 2)
    if (isFiltering) {
      filtered = filtered.filter((m) => {
        // B2.3: Normalize text for search (collapse whitespace) to match normalizedSearch
        const text = normalize((m.text || m.content || ''));
        const tag = normalize(((m.meta as any)?.tag || ''));
        const type = normalize(((m.meta as any)?.type || m.category || ''));
        
        return text.includes(normalizedSearch) || 
               tag.includes(normalizedSearch) || 
               type.includes(normalizedSearch);
      });
    }

    return { filteredMemories: filtered, duplicateCounts: duplicateCountsMap };
  }, [items, activeTab, showNoisyPinned, isFiltering, normalizedSearch, hideDuplicates, ageFilter, getDedupeKey, getItemAgeDays, normalize]);

  const tabs: { id: 'all' | 'notes' | 'facts' | 'sessions' | 'docs' | 'profile' | 'pinned'; label: string; icon?: React.ComponentType<{ className?: string }> }[] = [
    { id: 'all', label: 'All' },
    { id: 'notes', label: 'Notes' },
    { id: 'facts', label: 'Facts' },
    { id: 'profile', label: 'Profile' },
    { id: 'sessions', label: 'Sessions' },
    { id: 'docs', label: 'Docs' },
    { id: 'pinned', label: 'Pinned' },
  ];

  const hasProfileData = (p: ProfileData | null): boolean => {
    if (!p) return false;
    return Boolean(p.profile && p.profile.length > 0);
  };

  // Фильтрация мусорных фактов (только для UI, не трогает backend)
  const filterValidFact = (fact: string): boolean => {
    const trimmed = fact.trim();
    if (!trimmed) return false;
    
    // Игнорируем факты < 3 символов
    if (trimmed.length < 3) return false;
    
    // Игнорируем мусорные паттерны
    const lower = trimmed.toLowerCase();
    
    // FACTS_001, FACTS_002 и т.д.
    if (/^facts_\d+/i.test(trimmed)) return false;
    
    // Только цифры
    if (/^(\d+)$/.test(trimmed)) return false;
    
    // Начинается с "запомнил"
    if (/^запомнил/i.test(trimmed)) return false;
    
    // Содержит "запомни" как отдельное слово (legacy мусор)
    if (/\bзапомни\b/i.test(trimmed)) return false;
    
    // Игнорируем одно слово (но факты вида "predicate — object" пройдут, т.к. содержат "—")
    const words = trimmed.split(/\s+/);
    if (words.length === 1 && !trimmed.includes('—') && !trimmed.includes('-')) return false;
    
    return true;
  };

  const renderProfileTab = () => {
    if (!hasProfileData(profile)) {
      return (
        <div className="h-full flex flex-col items-center justify-center text-slate-600 space-y-4">
          <div className="w-16 h-16 rounded-full bg-purple-500/10 flex items-center justify-center border border-purple-500/30">
            <User className="w-8 h-8 opacity-60 text-purple-400" />
          </div>
          <span className="text-sm">
            {loading ? 'Loading profile from knowledge graph…' : 'No structured profile data yet.'}
          </span>
          <span className="text-[11px] text-slate-500 max-w-xs text-center">
            The assistant will slowly build your profile from chats and facts. Ask personal questions or state preferences to enrich it.
          </span>
        </div>
      );
    }

    const p = profile!;

    const section = (
      categoryKey: string,
      title: string,
      items?: string[],
      accentClasses?: string,
      Icon?: React.ComponentType<{ className?: string }>
    ) => {
      if (!items || items.length === 0) return null;
      
      // Фильтруем мусорные факты
      const validItems = items.filter(filterValidFact);
      if (validItems.length === 0) return null;
      
      const isOpen = profileCategoriesOpen[categoryKey] ?? true;
      
      return (
        <div className="glass-card rounded-2xl p-4 border border-white/10 bg-white/5 flex flex-col gap-2">
          <button
            onClick={() => setProfileCategoriesOpen(prev => ({ ...prev, [categoryKey]: !isOpen }))}
            className="flex items-center justify-between w-full"
          >
            <div
              className={`inline-flex items-center gap-2 text-[11px] font-semibold uppercase tracking-widest px-2.5 py-1 rounded-full border ${
                accentClasses || 'bg-purple-500/10 text-purple-300 border-purple-500/30'
              }`}
            >
              {Icon ? (
                <Icon className="w-3 h-3" />
              ) : (
                <Hash className="w-3 h-3" />
              )}
              {title}
            </div>
            <ChevronDown className={`w-4 h-4 text-slate-400 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
          </button>
          {isOpen && (
            <div className="flex flex-wrap gap-1.5 mt-1">
              {validItems.map((it) => (
                <span
                  key={it}
                  className="px-2 py-1 rounded-full bg-black/30 border border-white/10 text-[11px] text-slate-100"
                >
                  {it}
                </span>
              ))}
            </div>
          )}
        </div>
      );
    };

    // Показываем только profile секцию
    const categoryOrder = ['profile'];
    const categoryMap: Record<string, React.ReactNode> = {
      profile: section('profile', 'Profile', p.profile, 'bg-purple-500/15 text-purple-200 border-purple-500/40', User),
    };
    
    const sections = categoryOrder
      .map(key => categoryMap[key])
      .filter(Boolean);

    return (
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 animate-fade-in-up">
        {sections}
      </div>
    );
  };

  return (
    <div className="h-full flex flex-col p-8 relative overflow-hidden">
      {/* Header Section */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-end mb-8 gap-4 flex-shrink-0 animate-fade-in-up">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <div className="p-2 rounded-lg bg-air-500/10 text-air-500 border border-air-500/20 shadow-[0_0_15px_rgba(249,115,22,0.1)]">
              <Database className="w-5 h-5" />
            </div>
            <h2 className="text-2xl font-bold text-white tracking-tight">Store</h2>
          </div>
          <p className="text-sm text-slate-400 max-w-lg leading-relaxed ml-1">
            Documents, notes, and facts.
          </p>
        </div>

        {/* Filter Chips */}
        <div className="flex flex-wrap items-center gap-2">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-1.5 rounded-full text-[10px] font-bold uppercase tracking-wider transition-all duration-300 border flex items-center gap-1.5 ${
                activeTab === tab.id
                  ? tab.id === 'pinned'
                    ? 'bg-emerald-500 text-white border-emerald-500 shadow-[0_0_15px_rgba(16,185,129,0.3)] scale-105'
                    : 'bg-air-500 text-white border-air-500 shadow-[0_0_15px_rgba(249,115,22,0.3)] scale-105'
                  : 'bg-white/5 text-slate-500 border-white/5 hover:bg-white/10 hover:text-slate-300 hover:border-white/10'
              }`}
            >
              {tab.id === 'pinned' && <Pin className="w-3 h-3" />}
              {tab.label}
            </button>
          ))}
          
          {/* Show noisy pinned toggle - только для вкладки Pinned */}
          {activeTab === 'pinned' && (
            <label className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[10px] font-medium text-slate-400 border border-white/5 bg-white/5 hover:bg-white/10 cursor-pointer transition-colors">
              <input
                type="checkbox"
                checked={showNoisyPinned}
                onChange={(e) => setShowNoisyPinned(e.target.checked)}
                className="w-3 h-3 rounded border-white/20 bg-white/5 text-emerald-500 focus:ring-emerald-500/50 cursor-pointer"
              />
              <span>Show noisy pinned</span>
            </label>
          )}
        </div>
      </div>

      {/* Search Bar */}
      <div
        className="relative mb-6 flex-shrink-0 animate-fade-in-up"
        style={{ animationDelay: '0.1s' }}
      >
        <div className="absolute left-4 top-1/2 -translate-y-1/2 text-air-500/50">
          <Search className="w-5 h-5" />
        </div>
        <input
          type="text"
          placeholder="Search vectors..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="w-full glass-input rounded-2xl pl-12 pr-4 py-4 text-white placeholder-slate-600 focus:outline-none focus:border-air-500/50 focus:bg-white/5 transition-all text-sm shadow-inner border border-white/5"
        />
        {loading && activeTab !== 'profile' && (
          <div className="absolute right-4 top-1/2 -translate-y-1/2 text-air-500">
            <RefreshCw className="w-4 h-4 animate-spin" />
          </div>
        )}
        {/* B2.3: Hint about client-side filtering */}
        {isFiltering && (
          <div className="absolute bottom-0 left-12 translate-y-full mt-1 text-[10px] text-slate-500">
            Filtering loaded items. Use Load More to search further.
          </div>
        )}
      </div>

      {/* B3.1: Memory Hygiene Controls */}
      <div className="mb-4 flex-shrink-0 animate-fade-in-up" style={{ animationDelay: '0.15s' }}>
        <div className="flex flex-wrap items-center gap-3 p-3 rounded-xl bg-white/5 border border-white/10">
          {/* Hide Duplicates Toggle */}
          <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
            <input
              type="checkbox"
              checked={hideDuplicates}
              onChange={(e) => setHideDuplicates(e.target.checked)}
              className="w-3.5 h-3.5 rounded border-white/20 bg-white/5 text-air-500 focus:ring-air-500/50 cursor-pointer"
            />
            <span>Hide duplicates</span>
          </label>

          {/* Age Filter */}
          <div className="flex items-center gap-2">
            <Calendar className="w-3.5 h-3.5 text-slate-400" />
            <select
              value={ageFilter}
              onChange={(e) => setAgeFilter(e.target.value)}
              className="text-xs bg-white/5 border border-white/10 rounded px-2 py-1 text-slate-300 focus:outline-none focus:border-air-500/50"
            >
              <option value="all">All</option>
              <option value="7d">7d+</option>
              <option value="30d">30d+</option>
              <option value="90d">90d+</option>
            </select>
          </div>

          {/* C3.0: Show Archived Toggle */}
          <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
            <input
              type="checkbox"
              checked={showArchived}
              onChange={(e) => setShowArchived(e.target.checked)}
              className="w-3.5 h-3.5 rounded border-white/20 bg-white/5 text-air-500 focus:ring-air-500/50 cursor-pointer"
            />
            <span>Show archived</span>
          </label>

          {/* Select Mode Toggle */}
          <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer ml-auto">
            <input
              type="checkbox"
              checked={selectMode}
              onChange={(e) => {
                setSelectMode(e.target.checked);
                if (!e.target.checked) setSelectedIds(new Set());
              }}
              className="w-3.5 h-3.5 rounded border-white/20 bg-white/5 text-air-500 focus:ring-air-500/50 cursor-pointer"
            />
            <span>Select mode</span>
          </label>

          {/* Bulk Archive Button */}
          {selectMode && selectedIds.size > 0 && (
            <button
              onClick={archiveSelected}
              disabled={!!archivingProgress}
              className="px-3 py-1.5 rounded-lg text-xs font-medium text-white bg-amber-500/20 border border-amber-500/30 hover:bg-amber-500/30 hover:border-amber-500/50 transition-all flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {archivingProgress ? (
                <>
                  <RefreshCw className="w-3 h-3 animate-spin" />
                  Archiving {archivingProgress.current}/{archivingProgress.total}...
                </>
              ) : (
                <>
                  <Archive className="w-3 h-3" />
                  Archive selected ({selectedIds.size})
                </>
              )}
            </button>
          )}

          {/* Clear Selection */}
          {selectMode && selectedIds.size > 0 && (
            <button
              onClick={() => setSelectedIds(new Set())}
              className="px-3 py-1.5 rounded-lg text-xs font-medium text-slate-400 hover:text-slate-200 border border-white/10 hover:border-white/20 transition-all flex items-center gap-1"
            >
              <X className="w-3 h-3" />
              Clear
            </button>
          )}
        </div>
        <div className="mt-1 text-[10px] text-slate-500 ml-1">
          Filters apply to loaded items only. Use Load More to scan more.
        </div>
      </div>

      {/* B1.5: Bulk Delete Controls removed (read-only mode) */}

      {/* B2.5: Quick Capture */}
      <div className="mb-4 flex-shrink-0 animate-fade-in-up" style={{ animationDelay: '0.2s' }}>
        <div className="flex items-end gap-2">
          <div className="flex-1 relative">
            <textarea
              ref={captureTextareaRef}
              value={captureText}
              onChange={(e) => {
                setCaptureText(e.target.value);
                // Auto-resize textarea
                e.target.style.height = 'auto';
                e.target.style.height = `${Math.min(e.target.scrollHeight, 120)}px`;
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleCaptureSave();
                }
              }}
              placeholder="Quick capture… (minimum 5 characters)"
              rows={1}
              className="w-full glass-input rounded-xl pl-4 pr-20 py-2.5 text-white placeholder-slate-600 focus:outline-none focus:border-air-500/50 focus:bg-white/5 transition-all text-sm shadow-inner border border-white/5 resize-none overflow-hidden"
              style={{ minHeight: '40px', maxHeight: '120px' }}
              disabled={loadingCapture}
            />
            {captureStatus && (
              <div className="absolute right-12 top-1/2 -translate-y-1/2 text-xs text-emerald-400">
                {captureStatus}
              </div>
            )}
          </div>
          <button
            onClick={handleCaptureSave}
            disabled={loadingCapture || (captureText || "").trim().length < 5}  // C3.2: Match backend min 5 chars
            className="px-4 py-2.5 rounded-xl text-sm font-medium text-white bg-air-500/20 border border-air-500/30 hover:bg-air-500/30 hover:border-air-500/50 transition-all flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loadingCapture ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                Saving...
              </>
            ) : (
              'Save'
            )}
          </button>
        </div>
      </div>

      {/* Results List */}
      <div className="flex-1 overflow-y-auto space-y-3 custom-scrollbar -mr-4 pr-4 pb-4">
        {activeTab === 'profile' ? (
          renderProfileTab()
        ) : activeTab === 'facts' ? (
          <>
            {facts.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-slate-600 space-y-4">
                <div className="w-16 h-16 rounded-full bg-white/5 flex items-center justify-center">
                  <Filter className="w-8 h-8 opacity-20" />
                </div>
                <span className="text-sm">
                  {loading ? 'Loading facts...' : 'No facts found.'}
                </span>
              </div>
            ) : (
              facts.map((fact, index) => {
                return (
                <div
                  key={fact.id || index}
                  className="glass-card p-5 rounded-2xl hover:bg-white/[0.03] transition-all group border border-white/5 hover:border-amber-500/30 animate-fade-in-up relative"
                  style={{ animationDelay: `${index * 0.05}s` }}
                >
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <div className="text-[10px] font-bold uppercase tracking-widest px-2.5 py-1 rounded-md border bg-amber-500/10 text-amber-500 border-amber-500/20 flex items-center gap-2">
                        <Hash className="w-3 h-3" />
                        Fact
                      </div>
                      {fact.category && (
                        <div className={`text-[10px] font-bold uppercase tracking-widest px-2.5 py-1 rounded-md border flex items-center gap-2 ${
                          fact.category === 'profile' 
                            ? 'bg-purple-500/10 text-purple-400 border-purple-500/30'
                            : 'bg-slate-500/10 text-slate-400 border-slate-500/30'
                        }`}>
                          {fact.category}
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="space-y-2 mb-4">
                    <div className="text-slate-300 text-sm">
                      <span className="text-slate-500 text-xs">Subject:</span>{' '}
                      <span className="font-medium">{fact.subject}</span>
                    </div>
                    <div className="text-slate-300 text-sm">
                      <span className="text-slate-500 text-xs">Predicate:</span>{' '}
                      <span className="font-medium">{fact.predicate}</span>
                    </div>
                    <div className="text-slate-200 text-sm leading-relaxed font-medium pl-1 border-l-2 border-amber-500/40 group-hover:border-amber-500 transition-colors py-1">
                      <span className="text-slate-500 text-xs">Object:</span>{' '}
                      {fact.object}
                    </div>
                  </div>

                  <div className="flex items-center justify-between text-[10px] text-slate-500 font-mono border-t border-white/5 pt-3 mt-2">
                    <span className="flex items-center gap-2">
                      <span className="w-1.5 h-1.5 rounded-full bg-slate-700 group-hover:bg-amber-500 transition-colors" />
                      {fact.source_session && (
                        <>
                          Session: <span className="text-slate-400">{fact.source_session}</span>
                        </>
                      )}
                    </span>
                    <span className="opacity-70">
                      {new Date(fact.timestamp * 1000).toLocaleDateString()} •{' '}
                      {new Date(fact.timestamp * 1000).toLocaleTimeString()}
                    </span>
                  </div>
                </div>
                );
              })
            )}
          </>
        ) : !activeSessionId ? (
          <div className="h-full flex flex-col items-center justify-center text-slate-600 space-y-4">
            <div className="w-16 h-16 rounded-full bg-white/5 flex items-center justify-center">
              <Database className="w-8 h-8 opacity-20" />
            </div>
            <span className="text-sm">
              Select a chat to view session memory.
            </span>
          </div>
        ) : loading && items.length === 0 ? (
          // P2.3.2: Skeleton loading state
          <div className="space-y-4">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="glass-card p-5 rounded-2xl border border-white/5 animate-pulse">
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-white/10" />
                    <div className="h-4 w-24 bg-white/10 rounded" />
                  </div>
                  <div className="h-4 w-16 bg-white/10 rounded" />
                </div>
                <div className="space-y-2">
                  <div className="h-3 bg-white/5 rounded w-full" />
                  <div className="h-3 bg-white/5 rounded w-3/4" />
                </div>
              </div>
            ))}
          </div>
        ) : filteredMemories.length === 0 ? (
          // P2.3.2: Empty state
          <div className="h-full flex flex-col items-center justify-center text-slate-600 space-y-4">
            <div className="w-16 h-16 rounded-full bg-white/5 flex items-center justify-center">
              <Database className="w-8 h-8 opacity-20" />
            </div>
            <span className="text-sm font-medium text-slate-500">
              {isFiltering 
                ? 'No matches in loaded items.' 
                : 'No items yet'}
            </span>
            {/* P2.3.2: Helpful subtitle for empty state */}
            {!isFiltering && (
              <span className="text-xs text-slate-600 max-w-xs text-center">
                Save notes, facts, or promote chat messages to see them here.
              </span>
            )}
            {/* B2.3: Hint about Load More when filtering */}
            {isFiltering && items.length > 0 && (
              <span className="text-[11px] text-slate-500 max-w-xs text-center">
                Use Load More to search further.
              </span>
            )}
          </div>
        ) : (
          filteredMemories.map((memory, index) => {
            const { meta, clean } = splitMeta(memory.content || "");
            const itemIsArchived = isItemArchived(memory);  // P2.3.3: Check if item is archived
            
            return (
            <div
              key={memory.id}
              className={`glass-card p-5 rounded-2xl hover:bg-white/[0.03] transition-all group border animate-fade-in-up relative ${
                // P2.3.3: Dim archived items visually
                showArchived && itemIsArchived 
                  ? 'opacity-70 border-amber-500/20 hover:border-amber-500/40' 
                  : 'border-white/5 hover:border-air-500/30'
              }`}
              style={{ animationDelay: `${index * 0.05}s` }}
            >
              {/* B3.1: Select mode checkbox */}
              {selectMode && (
                <div className="absolute top-4 left-4 z-10">
                  <input
                    type="checkbox"
                    checked={selectedIds.has(memory.id)}
                    onChange={(e) => {
                      setSelectedIds(prev => {
                        const next = new Set(prev);
                        if (e.target.checked) {
                          next.add(memory.id);
                        } else {
                          next.delete(memory.id);
                        }
                        return next;
                      });
                    }}
                    className="w-4 h-4 rounded border-white/20 bg-white/5 text-air-500 focus:ring-air-500/50 cursor-pointer"
                  />
                </div>
              )}
              <div className={`flex items-start justify-between mb-3 ${selectMode ? 'pl-8' : ''} pr-8`}>
                <div className="flex items-center gap-2">
                  {/* Pinned badge */}
                  {(() => {
                    const metaTag = (memory.meta as any)?.tag;
                    const contentHasRagPin = memory.content.includes('[Meta:') && memory.content.includes('Tag: rag_pin');
                    const isPinned = metaTag === 'rag_pin' || contentHasRagPin;
                    if (isPinned) {
                      return (
                        <div className="text-[10px] font-bold uppercase tracking-widest px-2.5 py-1 rounded-md border flex items-center gap-2 bg-emerald-500/10 text-emerald-400 border-emerald-500/30">
                          <Pin className="w-3 h-3" />
                          Pinned
                        </div>
                      );
                    }
                    return null;
                  })()}
                  
                  {/* HOTFIX: badge should follow item.type (not namespace) */}
                  {(() => {
                    const badgeLabel = getBadgeLabel(memory);
                    const itemKind = getEffectiveKind(memory).toLowerCase();
                    
                    // Determine styles based on effective kind (includes namespace fallback)
                    const getBadgeStyles = () => {
                      if (itemKind === 'profile') {
                        return 'bg-purple-500/10 text-purple-500 border-purple-500/20';
                      } else if (itemKind === 'docs') {
                        return 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20';
                      } else if (itemKind === 'facts' || itemKind === 'fact') {
                        return 'bg-amber-500/10 text-amber-500 border-amber-500/20';
                      } else if (itemKind === 'chat') {
                        return 'bg-blue-500/10 text-blue-500 border-blue-500/20';
                      } else {
                        return 'bg-blue-500/10 text-blue-500 border-blue-500/20';
                      }
                    };
                    
                    return (
                      <div
                        className={`text-[10px] font-bold uppercase tracking-widest px-2.5 py-1 rounded-md border flex items-center gap-2 ${getBadgeStyles()}`}
                      >
                        <Hash className="w-3 h-3" />
                        {badgeLabel}
                      </div>
                    );
                  })()}
                  
                  {/* B3.1: Duplicate badge */}
                  {hideDuplicates && duplicateCounts && (() => {
                    const key = getDedupeKey(memory);
                    const count = duplicateCounts.get(key) || 0;
                    if (count > 1) {
                      return (
                        <div className="text-[9px] font-medium px-1.5 py-0.5 rounded bg-slate-500/20 text-slate-400 border border-slate-500/30">
                          dup x{count}
                        </div>
                      );
                    }
                    return null;
                  })()}
                  
                  {/* C3.0: Archived badge (only shown when showArchived is ON) */}
                  {showArchived && isItemArchived(memory) && (
                    <div className="text-[9px] font-medium px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-400 border border-amber-500/30">
                      Archived
                    </div>
                  )}
                  
                  {meta && (
                    <button
                      onClick={() => toggleMeta(memory.id)}
                      className="px-2 py-0.5 rounded-full text-[9px] font-medium text-slate-400 hover:text-slate-200 border border-white/5 bg-white/5 hover:bg-white/10 transition-colors flex items-center gap-1"
                      title="Toggle metadata"
                    >
                      {metaOpen[memory.id] ? (
                        <>
                          <ChevronDown className="w-2.5 h-2.5 rotate-180" />
                          <span>Meta</span>
                        </>
                      ) : (
                        <>
                          <Info className="w-2.5 h-2.5" />
                          <span>Meta</span>
                        </>
                      )}
                    </button>
                  )}
                </div>

                {memory.relevanceScore !== undefined && (
                  <div className="flex items-center gap-1.5 text-xs font-mono text-slate-400 bg-black/20 px-2 py-1 rounded-full border border-white/5">
                    <Zap
                      className={`w-3 h-3 ${
                        memory.relevanceScore > 0.8
                          ? 'text-amber-400 fill-amber-400'
                          : 'text-slate-600'
                      }`}
                    />
                    <span
                      className={
                        memory.relevanceScore > 0.8
                          ? 'text-amber-200'
                          : 'text-slate-500'
                      }
                    >
                      {(memory.relevanceScore * 100).toFixed(0)}% Match
                    </span>
                  </div>
                )}
              </div>

              {/* B2.2: Memory Bank action buttons */}
              {/* HOTFIX: Add Promote action + archive confirm */}
              <div className="absolute top-5 right-5 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                <div className="relative menu-dropdown-container">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setMenuOpen(prev => ({ ...prev, [memory.id]: !prev[memory.id] }));
                    }}
                    className="p-1.5 rounded-md text-slate-400 hover:text-slate-200 hover:bg-white/5 transition-colors"
                    title="More actions"
                  >
                    <MoreVertical className="w-4 h-4" />
                  </button>
                  {menuOpen[memory.id] && (
                    <div className="absolute right-0 top-8 z-50 bg-black/90 border border-white/10 rounded-lg shadow-lg min-w-[160px] py-1">
                      {/* C3.1: Promote... button */}
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setMenuOpen(prev => ({ ...prev, [memory.id]: false }));
                          setPromotePanelOpen(prev => ({ ...prev, [memory.id]: true }));
                        }}
                        className="w-full px-3 py-2 text-left text-xs text-slate-300 hover:bg-white/10 transition-colors"
                      >
                        Promote...
                      </button>
                      {/* C3.0: Show Archive or Unarchive based on item state */}
                      {isItemArchived(memory) ? (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setMenuOpen(prev => ({ ...prev, [memory.id]: false }));
                            handleUnarchive(memory.id, e);
                          }}
                          className="w-full px-3 py-2 text-left text-xs text-slate-300 hover:bg-white/10 transition-colors"
                        >
                          Unarchive
                        </button>
                      ) : (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setMenuOpen(prev => ({ ...prev, [memory.id]: false }));
                            handleArchive(memory.id, e);
                          }}
                          className="w-full px-3 py-2 text-left text-xs text-slate-300 hover:bg-white/10 transition-colors"
                        >
                          Archive
                        </button>
                      )}
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setMenuOpen(prev => ({ ...prev, [memory.id]: false }));
                          handleDelete(memory.id, e);
                        }}
                        className="w-full px-3 py-2 text-left text-xs text-red-400 hover:bg-white/10 transition-colors"
                      >
                        Delete
                      </button>
                    </div>
                  )}
                </div>
              </div>

              {/* C3.1: Promote panel (inline, shown when promotePanelOpen[memory.id] is true) */}
              {promotePanelOpen[memory.id] && (
                <div className="mb-4 p-3 bg-white/5 border border-white/10 rounded-lg">
                  <div className="text-xs font-medium text-slate-300 mb-3">Promote item</div>
                  <div className="flex flex-col gap-3">
                    <div>
                      <label className="block text-[10px] text-slate-400 mb-1">Type</label>
                      <select
                        id={`promote-type-${memory.id}`}
                        defaultValue="note"
                        className="w-full text-xs bg-white/5 border border-white/10 rounded px-2 py-1.5 text-slate-300 focus:outline-none focus:border-air-500/50"
                      >
                        <option value="note">Note</option>
                        <option value="chat">Chat</option>
                        <option value="fact">Fact</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-[10px] text-slate-400 mb-1">Tag</label>
                      <select
                        id={`promote-tag-${memory.id}`}
                        defaultValue="manual"
                        className="w-full text-xs bg-white/5 border border-white/10 rounded px-2 py-1.5 text-slate-300 focus:outline-none focus:border-air-500/50"
                      >
                        <option value="manual">Manual</option>
                        <option value="general">General</option>
                      </select>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={async (e) => {
                          e.stopPropagation();
                          const typeSelect = document.getElementById(`promote-type-${memory.id}`) as HTMLSelectElement;
                          const tagSelect = document.getElementById(`promote-tag-${memory.id}`) as HTMLSelectElement;
                          const targetType = typeSelect?.value as "chat" | "note" | "fact";
                          const targetTag = tagSelect?.value;
                          
                          if (targetType) {
                            await promoteItem(memory.id, targetType, targetTag);
                          }
                        }}
                        disabled={promoteLoading[memory.id]}
                        className="flex-1 px-3 py-1.5 text-xs font-medium text-white bg-air-500/20 border border-air-500/30 hover:bg-air-500/30 hover:border-air-500/50 transition-all rounded disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-1"
                      >
                        {promoteLoading[memory.id] ? (
                          <>
                            <RefreshCw className="w-3 h-3 animate-spin" />
                            Applying...
                          </>
                        ) : promoteSuccess[memory.id] ? (
                          <>
                            <Check className="w-3 h-3" />
                            Applied
                          </>
                        ) : (
                          'Apply'
                        )}
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setPromotePanelOpen(prev => {
                            const next = { ...prev };
                            delete next[memory.id];
                            return next;
                          });
                        }}
                        disabled={promoteLoading[memory.id]}
                        className="px-3 py-1.5 text-xs font-medium text-slate-300 hover:text-slate-200 border border-white/10 hover:border-white/20 transition-all rounded disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                </div>
              )}

              <p className="text-slate-200 text-sm leading-relaxed font-medium mb-4 pl-1 border-l-2 border-white/10 group-hover:border-air-500/50 transition-colors py-1">
                {/* B2.3: Render with highlight if filtering */}
                {isFiltering ? renderHighlighted(clean, normalizedSearch) : clean}
              </p>
              
              {meta && metaOpen[memory.id] && (() => {
                const metaObj = parseMeta(meta);
                const query = metaObj.Query || metaObj.query;
                const hasLongQuery = query && query.length > 40;
                const showQuery = queryOpen[memory.id];
                
                return (
                  <div className="mt-2 text-xs bg-black/20 border border-white/5 rounded-lg px-3 py-2">
                    <div className="grid gap-y-1 gap-x-3" style={{ gridTemplateColumns: 'auto 1fr' }}>
                      {metaObj.Source && (
                        <>
                          <span className="text-slate-500">Source:</span>
                          <span className={metaObj.Source === 'unknown' ? 'text-slate-500' : 'text-slate-300'}>
                            {metaObj.Source}
                          </span>
                        </>
                      )}
                      {metaObj.Tag && (
                        <>
                          <span className="text-slate-500">Tag:</span>
                          <span className="text-slate-300">{metaObj.Tag}</span>
                        </>
                      )}
                      {metaObj.OriginalTag && (
                        <>
                          <span className="text-slate-500">OriginalTag:</span>
                          <span className="text-slate-300">{metaObj.OriginalTag}</span>
                        </>
                      )}
                      {metaObj.Score && (
                        <>
                          <span className="text-slate-500">Score:</span>
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] bg-air-500/10 text-air-400 border border-air-500/30">
                            <Zap size={10} /> {metaObj.Score}
                          </span>
                        </>
                      )}
                      {metaObj.PinnedFrom && (
                        <>
                          <span className="text-slate-500">PinnedFrom:</span>
                          <span className="text-slate-300">{metaObj.PinnedFrom}</span>
                        </>
                      )}
                      {metaObj.Session && (
                        <>
                          <span className="text-slate-500">Session:</span>
                          <div className="flex items-center gap-1.5">
                            <span className="text-slate-300">{metaObj.Session}</span>
                            <button
                              onClick={() => handleCopySession(metaObj.Session, memory.id)}
                              className="p-0.5 hover:bg-white/10 rounded text-slate-400 hover:text-slate-200 transition-colors"
                              title={copiedSessionId === memory.id ? 'Copied' : 'Copy session id'}
                            >
                              {copiedSessionId === memory.id ? (
                                <ClipboardCheck size={12} className="text-emerald-400" />
                              ) : (
                                <Copy size={12} />
                              )}
                            </button>
                          </div>
                        </>
                      )}
                    </div>
                    {query && (
                      <div className="mt-2 pt-2 border-t border-white/5">
                        {hasLongQuery ? (
                          <>
                            <button
                              onClick={() => toggleQuery(memory.id)}
                              className="text-slate-400 hover:text-slate-200 text-[10px] font-medium transition-colors"
                            >
                              {showQuery ? 'Hide query' : 'Show query'}
                            </button>
                            {showQuery && (
                              <div className="mt-1 text-slate-300 font-mono break-words text-[10px]">
                                {query}
                              </div>
                            )}
                          </>
                        ) : (
                          <div className="flex items-start gap-2">
                            <span className="text-slate-500">Query:</span>
                            <span className="text-slate-300">{query}</span>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })()}

              <div className="flex items-center justify-between text-[10px] text-slate-500 font-mono border-t border-white/5 pt-3 mt-2">
                <span className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-slate-700 group-hover:bg-air-500 transition-colors" />
                  Source:{' '}
                  <span className="text-slate-400">
                    {memory.source || 'System Internal'}
                  </span>
                </span>
                <div className="flex items-center gap-2">
                  {/* B2.2: Promote quick actions */}
                  <div className="flex items-center gap-1">
                    <button
                      onClick={(e) => handlePromote(memory.id, 'notes', undefined, e)}
                      className="px-1.5 py-0.5 rounded text-[9px] text-slate-400 hover:text-blue-400 hover:bg-white/5 transition-colors border border-white/5"
                      title="Promote to notes"
                    >
                      →notes
                    </button>
                    <button
                      onClick={(e) => handlePromote(memory.id, 'chat', undefined, e)}
                      className="px-1.5 py-0.5 rounded text-[9px] text-slate-400 hover:text-blue-400 hover:bg-white/5 transition-colors border border-white/5"
                      title="Promote to chat"
                    >
                      →chat
                    </button>
                  </div>
                  <span className="opacity-70">
                    {new Date(memory.timestamp).toLocaleDateString()} •{' '}
                    {new Date(memory.timestamp).toLocaleTimeString()}
                  </span>
                </div>
              </div>
            </div>
            );
          })
        )}
        
        {/* B1: Load More button for pagination */}
        {/* B2.3: Show Load More even when filtering (to search further pages) */}
        {hasMore && activeSessionId && activeTab !== 'profile' && activeTab !== 'facts' && (
          <div className="flex flex-col items-center pt-4 gap-2">
            <button
              onClick={loadMore}
              disabled={loading}
              className="px-6 py-3 rounded-lg text-sm font-medium text-white bg-air-500/20 border border-air-500/30 hover:bg-air-500/30 hover:border-air-500/50 transition-all flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  Loading...
                </>
              ) : (
                <>
                  Load More
                </>
              )}
            </button>
            {/* P2.3.3: Load More helper line showing counts */}
            <div className="text-[10px] text-slate-500 text-center">
              {items.length > 0 && (
                <span>
                  Showing {filteredMemories.length} of {items.length} loaded
                  {isFiltering && items.length !== filteredMemories.length && (
                    <span className="block mt-0.5 text-slate-600">
                      Search is local. Load more to scan further.
                    </span>
                  )}
                </span>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Archive Confirmation Modal */}
      {showConfirmArchive && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div className="bg-slate-800 border border-white/10 rounded-lg shadow-lg p-6 max-w-md w-full mx-4">
            <h3 className="text-lg font-semibold text-white mb-4">Archive this item?</h3>
            <p className="text-sm text-slate-400 mb-6">
              This item will be archived and removed from the list.
            </p>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setShowConfirmArchive(null)}
                className="px-4 py-2 rounded-lg text-sm font-medium text-slate-300 hover:text-white border border-white/10 hover:border-white/20 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={confirmArchive}
                className="px-4 py-2 rounded-lg text-sm font-medium text-white bg-amber-500/20 border border-amber-500/30 hover:bg-amber-500/30 hover:border-amber-500/50 transition-colors"
              >
                Archive
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Undo Toast/Banner */}
      {pendingArchive && undoCountdown > 0 && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 bg-slate-800 border border-white/10 rounded-lg shadow-lg px-4 py-3 flex items-center gap-4 animate-fade-in-up">
          <span className="text-sm text-slate-300">
            Archived. Undo ({undoCountdown}s)
          </span>
          <button
            onClick={undoArchive}
            className="px-3 py-1.5 rounded-lg text-sm font-medium text-white bg-emerald-500/20 border border-emerald-500/30 hover:bg-emerald-500/30 hover:border-emerald-500/50 transition-colors"
          >
            Undo
          </button>
        </div>
      )}
    </div>
  );
};

export default Memory;