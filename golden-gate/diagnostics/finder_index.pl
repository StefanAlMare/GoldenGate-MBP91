use strict;
use warnings;
use Fcntl qw(:mode O_RDONLY O_NOFOLLOW O_NONBLOCK);
use MIME::Base64 qw(decode_base64);

my ($encoded, $user, $store) = @ARGV;
my $packed = decode_base64($encoded);
die "Lista UUID este incompletă.\n" unless length($packed) == 668*16;
my %expected = map { $_ => 1 } unpack('(a16)*', $packed);
die "Lista UUID conține duplicate.\n" unless keys(%expected) == 668;
alarm 45;

sub file_state {
    my ($path) = @_;
    my @s = lstat($path);
    return ($!{ENOENT} ? 'absent' : 'inaccesibil') unless @s;
    return ('alt_tip') unless S_ISREG($s[2]);
    return ($s[7] > 0 ? 'prezent' : 'gol', @s);
}

sub metadata {
    my ($label, $path, @keys) = @_;
    my ($state) = file_state($path);
    if ($state ne 'prezent') { print "$label | $state\n"; return }
    my %values;
    for my $key (@keys) {
        open my $fh, '-|', '/usr/bin/plutil', '-extract', $key, 'raw', '-o', '-', $path or next;
        my $value = <$fh>;
        next unless close($fh) && defined($value);
        chomp $value;
        $values{$key} = $value if $value =~ /\A[A-Za-z0-9_.-]{1,64}\z/;
    }
    print "$label | ", join(' ', map { "$_=" . ($values{$_} // 'indisponibil') } @keys), "\n";
    return %values;
}

my %states;
sub unit_state {
    my ($bytes) = @_;
    return $states{$bytes} if exists $states{$bytes};
    my $uuid = uc join '-', unpack('H8H4H4H4H12', $bytes);
    my ($state) = file_state("$store/$uuid.isdata");
    ($state) = file_state("$store/" . lc($uuid) . ".isdata") if $state eq 'absent';
    return $states{$bytes} = $state;
}

sub coverage {
    my ($label, $ids) = @_;
    my %counts;
    $counts{unit_state($_)} += $ids->{$_} for keys %$ids;
    print "$label | ", join(' ', map { "$_=" . ($counts{$_} // 0) }
        qw(prezent absent gol alt_tip inaccesibil)), "\n";
}

print "Golden B | utilizator de consolă UID=$> | verificare în regim de citire\n";
my %user_meta = metadata('Metadate index utilizator', "$user/__cache_info__", 'ProductBuildVersion', 'language');
my %store_meta = metadata('Metadate depozit comun', "$store/store-info.plist", 'version', 'language');
if (defined $user_meta{language} && defined $store_meta{language}) {
    print 'Limbă index/depozit | ', ($user_meta{language} eq $store_meta{language} ? 'coincide' : 'diferă'), "\n";
}
coverage('Cele 668 de unități din manifest în depozitul B', \%expected);
print "«prezent» înseamnă fișier obișnuit de mărime nenulă. Comparația este după nume.\n";

my $index = "$user/store.index";
my ($state, @s) = file_state($index);
if ($state ne 'prezent') { print "Index utilizator | $state\n"; exit($state eq 'absent' ? 0 : 3) }
die "Indexul are alt proprietar sau o dimensiune neașteptată.\n" if $s[4] != $> || $s[7] < 20 || $s[7] > 16*1024*1024;
sysopen my $fh, $index, O_RDONLY | O_NOFOLLOW | O_NONBLOCK or die "Indexul nu poate fi citit: $!\n";
binmode $fh;
my @before = stat($fh);
die "Indexul s-a schimbat înainte de citire.\n" unless @before && S_ISREG($before[2]) &&
    join(',', @before[0,1,4,7,9,10]) eq join(',', @s[0,1,4,7,9,10]);
my $n = read($fh, my $data, $s[7]+1);
my @after = stat($fh);
my @live = lstat($index);
die "Indexul s-a schimbat sau citirea a fost incompletă.\n" unless defined($n) && $n == $s[7] &&
    @after && @live && join(',', @after[0,1,7,9,10]) eq join(',', @live[0,1,7,9,10]) &&
    join(',', @before[7,9,10]) eq join(',', @after[7,9,10]);
my ($v, $one, $rows, $buckets, $heap) = unpack('V5', $data);
print "Index utilizator | octeți=$n versiune=$v înregistrări_declarate=$rows\n";
my $start = 20 + 8*$buckets;
die "Structura nu corespunde indexului v11 cu înregistrări de 172 de octeți.\n"
    unless $v == 11 && $one == 1 && $rows <= 65536 && $buckets >= 1 && $buckets <= 65536 &&
           $heap == $rows*172 && $start+$heap <= $n;
my %refs;
for my $i (0..$rows-1) { ++$refs{substr($data, $start+172*$i+96, 16)} }
my %unique = map { $_=>1 } keys %refs;
my $in_manifest = grep { exists $expected{$_} } keys %refs;
print "Câmp UUID presupus la offsetul empiric 96 | distincte=", scalar(keys %refs), " dintre_care_în_manifest=$in_manifest\n";
coverage('UUID distincte ale indexului în depozitul B', \%unique);
coverage('Înregistrări ale indexului după unitatea corespunzătoare din B', \%refs);
