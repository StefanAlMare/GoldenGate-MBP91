#!/bin/bash
# Snapshot of named Finder user clients in the IOAccelerator subtrees.
finder_gpu_clients() (
    local pid=${1:-} result
    if [[ ! $pid =~ ^[1-9][0-9]*$ ]]; then
        echo 'IORegistry: PID Finder indisponibil.'
        return
    fi
    set -o pipefail
    if ! result=$(
        /usr/bin/perl -e 'alarm 10; exec @ARGV or die $!' /usr/sbin/ioreg -p IOService -r -c IOAccelerator -l -w 220 2>/dev/null |
        /usr/bin/perl -e '
            use strict; use warnings;
            my $pid = shift;
            my ($root, $node, $node_id, %matches, %seen);
            while (<STDIN>) {
                if (/^([| ]*)\+-o /) {
                    my $is_root = !length($1);
                    $root = undef if $is_root;
                    ($node, $node_id) = ();
                    next unless /\+-o ([\w .@,+-]+?)\s+<class ([\w.-]+), id (0x[\da-f]+),/i;
                    if ($is_root) {
                        $root = "$1 ($2, $3)";
                    } else {
                        ($node, $node_id) = ($2, $3);
                    }
                    next;
                }
                next unless defined($root) && defined($node);
                next unless /^[| ]*"IOUserClientCreator"\s*=\s*"pid\s+\Q$pid\E,\s*Finder"\s*$/;
                ++$matches{$root}{$node} unless $seen{$node_id}++;
            }
            for my $root (sort keys %matches) {
                my @rows = map { "$_ × $matches{$root}{$_}" } sort keys %{$matches{$root}};
                print "Finder PID $pid | accelerator: $root | clienți IORegistry: ", join(", ", @rows), "\n";
            }
        ' "$pid"
    ); then
        echo 'IORegistry: inventarul clienților grafici este incomplet.'
    elif [[ -n $result ]]; then
        printf '%s\n' "$result"
        echo 'Un client înregistrat indică deschiderea acceleratorului. Activitatea de randare la momentul blocajului rămâne de stabilit.'
    else
        echo 'IORegistry: niciun client Finder identificabil în subarborii vizibili. GPU-ul folosit de Finder rămâne nedeterminat.'
    fi
)
