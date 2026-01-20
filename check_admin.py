#!/usr/bin/env python3
"""
Script pour vérifier et créer/réparer le compte administrateur
"""

import os
import sys
import hashlib

# Importer l'application et la base de données depuis app.py
from app import app, db, User

with app.app_context():
    
    print("🔍 Vérification du compte administrateur...")
    print("-" * 50)
    
    # Vérifier si un admin existe
    admin_email = 'admin@colourful.com'
    admin = User.query.filter_by(email=admin_email).first()
    
    if admin:
        print(f"✅ Compte admin trouvé:")
        print(f"   📧 Email: {admin.email}")
        print(f"   👤 Username: {admin.username}")
        print(f"   👤 Nom: {admin.nom} {admin.prenom}")
        print(f"   🔐 Password Hash: {admin.password_hash[:20]}...")
        print(f"   👑 Is Admin: {admin.is_admin}")
        print(f"   📅 Créé le: {admin.created_at}")
        
        # Vérifier le hash du mot de passe
        test_password = 'Admin@123456'
        expected_hash = hashlib.sha256(test_password.encode()).hexdigest()
        print(f"\n🔐 Test du mot de passe '{test_password}':")
        print(f"   Hash attendu: {expected_hash[:20]}...")
        print(f"   Hash actuel:  {admin.password_hash[:20]}...")
        
        if admin.password_hash == expected_hash:
            print("   ✅ Le mot de passe correspond!")
        else:
            print("   ❌ Le mot de passe ne correspond PAS!")
            print("\n🔧 Correction du mot de passe...")
            admin.password_hash = expected_hash
            db.session.commit()
            print("   ✅ Mot de passe mis à jour!")
        
        if not admin.is_admin:
            print("\n⚠️  L'utilisateur n'a pas les droits admin!")
            print("🔧 Activation des droits admin...")
            admin.is_admin = True
            db.session.commit()
            print("   ✅ Droits admin activés!")
        
        print("\n✅ Le compte admin est maintenant prêt à l'emploi!")
        print(f"   📧 Email: {admin_email}")
        print(f"   🔑 Mot de passe: {test_password}")
        
    else:
        print(f"❌ Aucun compte admin trouvé avec l'email: {admin_email}")
        print("\n🔧 Création du compte administrateur...")
        
        admin_password = 'Admin@123456'
        new_admin = User(
            email=admin_email,
            username='admin',
            password_hash=hashlib.sha256(admin_password.encode()).hexdigest(),
            nom='Admin',
            prenom='Principal',
            telephone='',
            is_admin=True
        )
        db.session.add(new_admin)
        db.session.commit()
        
        print("✅ Compte administrateur créé avec succès!")
        print(f"   📧 Email: {admin_email}")
        print(f"   🔑 Mot de passe: {admin_password}")
    
    print("\n" + "-" * 50)
    print(f"📊 Total d'administrateurs: {User.query.filter_by(is_admin=True).count()}")
    print(f"📊 Total d'utilisateurs: {User.query.filter_by(is_admin=False).count()}")
    
    # Afficher tous les admins
    all_admins = User.query.filter_by(is_admin=True).all()
    if all_admins:
        print("\n👥 Liste des administrateurs:")
        for admin in all_admins:
            print(f"   • {admin.email} ({admin.nom} {admin.prenom})")
