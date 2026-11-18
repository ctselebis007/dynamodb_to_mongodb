/**
 * Cluster sizing for the future volumes in Sample_Queries_Criteria.md §4.
 * Per-document figures were measured on the seeded demo database (collStats, November 2026).
 */

export const MB = 1024 ** 2
export const GB = 1024 ** 3

/** Measured on talent_quads (15,651 docs) after several graph reloads, so index sizes are on the high side. */
export const QUAD = {
  dataBytes: 248, // avgObjSize
  storageBytes: 274, // storageSize / count
  indexBytes: 805, // totalIndexSize / count (4 B-tree indexes)
  labelBytes: 33, // subject_label + object_label, the fields in the Search index
}

/** Measured on aicp_items: about 408 items per snapshot (2,487 facts), 1,024-dim embedding per item. */
export const SNAPSHOT = {
  items: 408,
  dataBytes: 15_740, // avgObjSize; the embedding stored as 1,024 doubles is most of it
  storageBytes: 29_370,
  indexBytes: 240,
  dims: 1024,
}

/** Estimates, not measurements: confirm with the Atlas Search index-size metric. */
export const SEARCH = {
  textBytesPerQuad: QUAD.labelBytes * 1.5 + 100, // tokens + per-document overhead
  vectorBytesPerItem: SNAPSHOT.dims * 4 * 1.1, // float32 + HNSW graph
}

export interface Horizon {
  id: string
  label: string
  quads: number
  driver: string
}

export const HORIZONS: Horizon[] = [
  { id: 'current', label: 'Current', quads: 15_651, driver: 'Measured, November 2026' },
  { id: 'near', label: 'Near term', quads: 300_000, driver: 'Security groups, repos, budgets, app inventory' },
  { id: 'horizon-1m', label: 'Horizon (low)', quads: 1_000_000, driver: 'Many more enterprise sources' },
  { id: 'horizon-3m', label: 'Horizon (high)', quads: 3_000_000, driver: '"Low single-digit millions"' },
]

export const OTHER_STORES_QUADS = 487_500
export const SNAPSHOT_OPTIONS = [2, 30, 90, 365]

export interface ClusterTier {
  name: string
  ramGB: number
  vcpu: number
  storageGB: number
}

/** AWS general class; M10/M20 are burstable and not recommended for production, so M30 is the floor. */
export const CLUSTER_TIERS: ClusterTier[] = [
  { name: 'M30', ramGB: 8, vcpu: 2, storageGB: 40 },
  { name: 'M40', ramGB: 16, vcpu: 4, storageGB: 80 },
  { name: 'M50', ramGB: 32, vcpu: 8, storageGB: 160 },
  { name: 'M60', ramGB: 64, vcpu: 16, storageGB: 320 },
  { name: 'M80', ramGB: 128, vcpu: 32, storageGB: 750 },
]

/** AWS High-CPU search tiers in us-east-1. S20 is the Atlas default and the production minimum. */
export const SEARCH_TIERS: ClusterTier[] = [
  { name: 'S20', ramGB: 4, vcpu: 2, storageGB: 98 },
  { name: 'S30', ramGB: 8, vcpu: 4, storageGB: 198 },
  { name: 'S40', ramGB: 16, vcpu: 8, storageGB: 396 },
  { name: 'S50', ramGB: 32, vcpu: 16, storageGB: 796 },
  { name: 'S60', ramGB: 64, vcpu: 32, storageGB: 1592 },
]

/** WiredTiger cache is 50% of (RAM - 1 GB); keep the working set under 70% of it. */
export const wiredTigerCacheGB = (t: ClusterTier) => 0.5 * (t.ramGB - 1)
const CACHE_HEADROOM = 0.7
/** Staged reload (two copies of a graph), oplog and growth. */
const DISK_HEADROOM = 2
/** mongot keeps ~1 GB for itself; the vector index must fit in RAM, text should. */
const SEARCH_RESERVED_GB = 1
/** Index rebuilds need a second copy, plus the 20% local-SSD overhead. */
const SEARCH_DISK_FACTOR = 2 * 1.2

export interface Sizing {
  quads: number
  aicpItems: number
  diskBytes: number
  workingSetBytes: number
  textIndexBytes: number
  vectorIndexBytes: number
  cluster: ClusterTier
  search: ClusterTier
}

const pick = (tiers: ClusterTier[], fits: (t: ClusterTier) => boolean) =>
  tiers.find(fits) ?? tiers[tiers.length - 1]

export function size(quads: number, snapshots: number): Sizing {
  const aicpItems = snapshots * SNAPSHOT.items
  const diskBytes =
    quads * (QUAD.storageBytes + QUAD.indexBytes) + aicpItems * (SNAPSHOT.storageBytes + SNAPSHOT.indexBytes)
  // Graph queries touch any quad, so all quad data and indexes are hot. AICP: every index, plus the
  // LIVE and one base snapshot (A5 diffs them); older snapshots stay on disk.
  const workingSetBytes =
    quads * (QUAD.dataBytes + QUAD.indexBytes) +
    aicpItems * SNAPSHOT.indexBytes +
    Math.min(snapshots, 2) * SNAPSHOT.items * SNAPSHOT.dataBytes
  const textIndexBytes = quads * SEARCH.textBytesPerQuad
  const vectorIndexBytes = aicpItems * SEARCH.vectorBytesPerItem
  const searchBytes = textIndexBytes + vectorIndexBytes

  const cluster = pick(
    CLUSTER_TIERS,
    (t) => workingSetBytes <= wiredTigerCacheGB(t) * CACHE_HEADROOM * GB && diskBytes * DISK_HEADROOM <= t.storageGB * GB,
  )
  const search = pick(
    SEARCH_TIERS,
    (t) => searchBytes <= (t.ramGB - SEARCH_RESERVED_GB) * GB && searchBytes * SEARCH_DISK_FACTOR <= t.storageGB * GB,
  )
  return { quads, aicpItems, diskBytes, workingSetBytes, textIndexBytes, vectorIndexBytes, cluster, search }
}

/** Quads at which the working set outgrows a tier's cache budget (AICP share ignored). */
export function quadCeiling(t: ClusterTier): number {
  return Math.floor((wiredTigerCacheGB(t) * CACHE_HEADROOM * GB) / (QUAD.dataBytes + QUAD.indexBytes))
}

export function formatBytes(bytes: number): string {
  if (bytes >= 1000 * MB) return `${(bytes / GB).toFixed(bytes >= 10 * GB ? 0 : 1)} GB`
  if (bytes >= MB) return `${Math.round(bytes / MB).toLocaleString()} MB`
  return `${Math.max(1, Math.round(bytes / 1024))} KB`
}
