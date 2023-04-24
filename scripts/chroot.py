import command_utils as cmd
import output_utils  as output

class Chroot:

    def __init__(self, target_mountpoint: str="/mnt", dry_run=False):
        # Mount all temporary API filesystems
        cmd.execute(f"mount -t proc /proc {target_mountpoint}/proc/", dry_run=dry_run)
        cmd.execute(f"mount --rbind /sys {target_mountpoint}/sys/", dry_run=dry_run)
        cmd.execute(f"mount --make-rslave {target_mountpoint}/sys/", dry_run=dry_run)
        cmd.execute(f"mount --rbind /dev {target_mountpoint}/dev/", dry_run=dry_run)
        cmd.execute(f"mount --make-rslave {target_mountpoint}/dev/", dry_run=dry_run)
        cmd.execute(f"mount --rbind /run {target_mountpoint}/run/", dry_run=dry_run)
        cmd.execute(f"mount --make-slave {target_mountpoint}/run/", dry_run=dry_run)

        # Mount EFI variables for UEFI bootloader configuration
        cmd.execute(
            f"mount --rbind /sys/firmware/efi/efivars {target_mountpoint}/sys/firmware/efi/efivars",
            dry_run=dry_run)

        # Copy DNS details to new root
        cmd.execute(f"cp /etc/resolv.conf {target_mountpoint}/etc/resolv.conf", dry_run=dry_run)

        self.target  = target_mountpoint
        self.dry_run = dry_run

    def __enter__(self):
        return self

    def __wrap_chroot(self, command, std_code: int=3, wait_for_proc=True):
        return cmd.execute(f"chroot {self.target} sh -c '{command}'", std_code, self.dry_run, wait_for_proc)

    def configure_clock(self, timezone: str="",
                              hardware_utc: bool=True,
                              enable_ntp: bool=True):

        # Create a symlink from the timezone file to /etc/localtime
        if timezone:
            cmd.execute(
                f"ln -sf {self.target}/usr/share/zoneinfo/{timezone} {self.target}/etc/localtime",
                dry_run=self.dry_run
            )

        # Configure the hardware clock to system time (with UTC if desired)
        self.__wrap_chroot(f"hwclock --systohc {'--utc' if hardware_utc else ''}")

        # Enable systemd-timesyncd if desired
        if enable_ntp:
            self.__wrap_chroot("systemctl enable systemd-timesyncd")

    def configure_locales(self, locale_gen: list=["en_US.UTF-8 UTF-8"],
                                locale_conf: str="en_US.UTF-8"):

        # Uncomment each specified locale in /etc/locale.gen
        with open(f"{self.target}/etc/locale.gen", "r") as locale_gen_file:
            locale_file_data = locale_gen_file.read()

        for locale in locale_gen:
            locale_file_data = locale_file_data.replace(f"#{locale}", locale)

        with open(f"{self.target}/etc/locale.gen", "w") as locale_gen_file:
            locale_gen_file.write(locale_file_data)

        # Generate locales
        self.__wrap_chroot("locale-gen")

        # Set the LANG variable to desired locale
        with open(f"{self.target}/etc/locale.conf", "w") as locale_conf_file:
            locale_conf_file.write(f"LANG={locale_conf}")

    def configure_hosts(self):
        # Add localhost entries in /etc/hosts for both IPv4 and IPv6
        with open(f"{self.target}/etc/hosts", "a") as hosts_file:
            hosts_file.write("127.0.0.1\tlocalhost\n")
            hosts_file.write("::1\t\t\tlocalhost\n")

    def set_hostname(self, hostname: str="myhostname"):
        with open(f"{self.target}/etc/hostname", "w") as hostname_file:
            hostname_file.write(hostname)

    def configure_users(self, root_password: str="",
                              users: dict={}):
        
        root_password_proc = self.__wrap_chroot("passwd", 7, wait_for_proc=False)
        if not self.dry_run:
            root_password_proc.communicate(f"{root_password}\n{root_password}".encode())

        # Build a list of groups that exist
        system_groups = []
        with open(f"{self.target}/etc/group", "r") as groups_file:
            for groupline in groups_file.readlines():
                system_groups.append(groupline.split(":")[0])

        for user in users:
            self.__wrap_chroot(f"useradd {user}")

            if shell := users[user]["shell"]:
                # Check to see if the specified shell is installed
                with open(f"{self.target}/etc/shells", "r") as shells_file:
                    shell_installed = False
                    for shell_line in shells_file.readlines()[3:]:
                        if shell_line.strip() == shell:
                            shell_installed = True

                    if not shell_installed:
                        self.__wrap_chroot(f"pacman --noconfirm -S {shell.split('/')[-1]}")
                        
                self.__wrap_chroot(f"usermod -s {shell} {user}")

            if comment := users[user]["comment"]:
                self.__wrap_chroot(f"usermod -c {comment} {user}")
            
            if groups := users[user]["groups"]:
                for group in groups:
                    # Create group if it doesn't exist
                    if group not in system_groups:
                        self.__wrap_chroot(f"groupadd {group}")

                    self.__wrap_chroot(f"usermod -a -G {group} {user}")

            passwd_proc = self.__wrap_chroot(f"passwd {user}", 7, wait_for_proc=False)
            if not self.dry_run:
                passwd_proc.communicate(
                    f"{users[user]['password']}\n{users[user]['password']}".encode())

    def exit(self):
        # Unmount all API filesystems from new root
        cmd.execute(f"umount -R {self.target}/proc/", dry_run=self.dry_run)
        cmd.execute(f"umount -R {self.target}/sys/", dry_run=self.dry_run)
        cmd.execute(f"umount -R {self.target}/dev/", dry_run=self.dry_run)
        cmd.execute(f"umount -R {self.target}/run/", dry_run=self.dry_run)
        cmd.execute(f"umount -R {self.target}/sys/firmware/efi/efivars", dry_run=self.dry_run)

    def __exit__(self, exc_type, exc_value, traceback):
        self.exit()


