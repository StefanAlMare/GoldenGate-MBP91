#import <Foundation/Foundation.h>
#import <OSLog/OSLog.h>
#include <stdio.h>
int main(int argc,char **argv){
 @autoreleasepool {
  if(argc!=2)return 2;
  NSError *error=nil;
  NSURL *url=[NSURL fileURLWithPath:[NSString stringWithUTF8String:argv[1]] isDirectory:YES];
  OSLogStore *store=[OSLogStore storeWithURL:url error:&error];
  if(!store){fprintf(stderr,"store: %s\n",error.description.UTF8String);return 3;}
  OSLogEnumerator *entries=[store entriesEnumeratorWithOptions:0 position:nil predicate:nil error:&error];
  if(!entries){fprintf(stderr,"enumerator: %s\n",error.description.UTF8String);return 4;}
  unsigned count=0,selected=0;
  for(OSLogEntry *entry in entries){
    @autoreleasepool {
     ++count;
     NSString *text=entry.composedMessage;
     pid_t pid=[entry respondsToSelector:@selector(processIdentifier)]?[(id<OSLogEntryFromProcess>)entry processIdentifier]:-1;
     NSString *proc=nil;
     if([entry respondsToSelector:@selector(process)]) proc=[(id<OSLogEntryFromProcess>)entry process];
     if((pid==0 && entry.date.timeIntervalSince1970>1795045343.54 && entry.date.timeIntervalSince1970<1795045345.4) || ((pid==1||pid==162||pid==117||pid==309||pid==341||pid==344||pid==164||pid==336) && entry.date.timeIntervalSince1970>1795045340 && entry.date.timeIntervalSince1970<1795045390) || [proc localizedCaseInsensitiveContainsString:@"diskimages"] ||
        [proc isEqualToString:@"mbsystemadministration"]||
        [text localizedCaseInsensitiveContainsString:@"DIDevice"] || [text localizedCaseInsensitiveContainsString:@"diskimage"] || [text localizedCaseInsensitiveContainsString:@"[344 (ctx)]"] || [text localizedCaseInsensitiveContainsString:@"[341 (ctx)]"]||
        [text localizedCaseInsensitiveContainsString:@"DiskImageParamsRAM"]){
      printf("%.6f\t%d\t%s\t%s\n",entry.date.timeIntervalSince1970-1795045265.,pid,proc.UTF8String,text.UTF8String);++selected;
     }
    }
   }
  fprintf(stderr,"total=%u selected=%u\n",count,selected);
  return count?0:5;
 }
}
