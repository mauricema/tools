#pragma pack(1)

typedef struct {
  UINT32    Signature;
  UINT32    Flags;
  UINT32    Offset;
  UINT32    Size;
} FLASH_MAP_ENTRY_DESC;

typedef struct {
  UINT32                Signature;
  UINT16                Version;
  UINT16                Length;
  UINT8                 Attributes;
  UINT8                 Reserved[3];
  UINT32                RomSize;
  FLASH_MAP_ENTRY_DESC  EntryDesc[];
} FLASH_MAP;

typedef struct {
  UINT16             BuildNumber;
  UINT8              ProjMinorVersion;
  UINT8              ProjMajorVersion;
  UINT8              CoreMinorVersion;
  UINT8              CoreMajorVersion;
  UINT8              SecureVerNum;
  UINT8              Reserved : 4;
  UINT8              ImageArch: 1;
  UINT8              BldDebug : 1;
  UINT8              FspDebug : 1;
  UINT8              Dirty    : 1;
} IMAGE_BUILD_INFO;

typedef struct {
  UINT32             Signature;
  UINT16             HeaderLength;
  UINT8              HeaderRevision;
  UINT8              Reserved;
  UINT64             ImageId;
  IMAGE_BUILD_INFO   ImageVersion;
  UINT64             SourceVersion;
} BOOT_LOADER_VERSION;

typedef struct {
  UINT8                Revision;
  UINT8                Reserved0[3];
  BOOT_LOADER_VERSION  Version;
} EXT_BOOT_LOADER_VERSION;

#pragma pack()